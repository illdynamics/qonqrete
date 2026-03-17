/**
 * QonQrete Project Service
 * Core service handling shell detection, execution, and state tracking
 * 
 * v1.1.9 PRODUCTION HARDENING:
 * - Uses CommandBuilder for all command assembly
 * - Deterministic repo discovery with persistence
 * - Daemon threads for marker watching (proper JVM shutdown)
 * - Refresh callbacks for auto-refresh after run completes
 * - All settings properly implemented and used
 *
 * @author WoNQ
 * @version 1.2.0
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.services

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessAdapter
import com.intellij.execution.process.ProcessEvent
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectRootManager
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.util.Key
import com.intellij.openapi.util.SystemInfo
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.openapi.wm.ToolWindowManager
import org.jetbrains.plugins.terminal.TerminalToolWindowManager
import sh.qonqrete.intellij.util.CommandBuilder
import sh.qonqrete.intellij.util.QonQreteValidation
import sh.qonqrete.intellij.util.ShellEscape
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicReference

typealias RunStateChangeCallback = (RunStatus) -> Unit
typealias ShellStateChangeCallback = (ShellInfo) -> Unit
typealias RefreshCallback = () -> Unit

@Service(Service.Level.PROJECT)
class QonQreteProjectService(private val project: Project) : Disposable {

    private val log = Logger.getInstance(QonQreteProjectService::class.java)
    private var shellInfo: ShellInfo = detectShell()
    private var runStatus = AtomicReference(RunStatus())
    private val runStateCallbacks = CopyOnWriteArrayList<RunStateChangeCallback>()
    private val shellStateCallbacks = CopyOnWriteArrayList<ShellStateChangeCallback>()
    private val refreshCallbacks = CopyOnWriteArrayList<RefreshCallback>()
    
    // Path discovery state - persisted per-project
    private var persistedQonqretePath: String? = null
    private var cachedVersion: String? = null
    
    @Volatile private var verificationInProgress = false
    @Volatile private var markerWatcherActive = false
    private var currentMarkerPath: Path? = null
    private var markerWatcherThread: Thread? = null

    companion object {
        private const val TERMINAL_NAME = "QonQrete Engine"
        
        @JvmStatic
        fun getInstance(project: Project): QonQreteProjectService {
            return project.getService(QonQreteProjectService::class.java)
        }
    }

    init {
        log.info("QonQrete Project Service initialized. Shell: ${shellInfo.shellType} at ${shellInfo.shellPath}")
        setupFileWatcher()
    }

    private fun setupFileWatcher() {
        project.messageBus.connect(this).subscribe(VirtualFileManager.VFS_CHANGES, object : BulkFileListener {
            override fun after(events: List<VFileEvent>) {
                for (event in events) {
                    val path = event.path
                    if (path.contains(".qonqrete_run_") && path.endsWith(".marker")) {
                        handleMarkerFileDetected(path)
                    }
                }
            }
        })
    }

    // ========================================================================
    // SHELL DETECTION
    // ========================================================================

    private fun detectShell(): ShellInfo {
        val settings = QonQreteSettingsState.getInstance()
        
        // Custom bash path takes priority if valid
        if (settings.customBashPath.isNotEmpty()) {
            val customPath = File(settings.customBashPath)
            if (customPath.exists() && customPath.canExecute()) {
                log.info("Using custom bash path: ${settings.customBashPath}")
                return ShellInfo(settings.customBashPath, SystemInfo.isWindows, true, "custom")
            }
            log.warn("Custom bash path not found or not executable: ${settings.customBashPath}")
        }

        if (!SystemInfo.isWindows) {
            // Unix: Check SHELL env, then common paths
            val envShell = System.getenv("SHELL")
            if (envShell != null && envShell.contains("bash") && File(envShell).exists()) {
                return ShellInfo(envShell, false, true, "bash")
            }
            if (File("/bin/bash").exists()) return ShellInfo("/bin/bash", false, true, "bash")
            if (File("/usr/bin/bash").exists()) return ShellInfo("/usr/bin/bash", false, true, "bash")
            return ShellInfo("", false, false, "none", ShellState.NO_BASH)
        }

        // Windows: Check GIT_BASH env, then common paths
        System.getenv("GIT_BASH")?.let { if (File(it).exists()) return ShellInfo(it, true, true, "env") }

        val bashPaths = mutableListOf<Pair<String, String>>()
        System.getenv("PROGRAMFILES")?.let { bashPaths.add(Pair("$it\\Git\\bin\\bash.exe", "gitbash")) }
        System.getenv("PROGRAMFILES(X86)")?.let { bashPaths.add(Pair("$it\\Git\\bin\\bash.exe", "gitbash")) }
        bashPaths.addAll(listOf(
            Pair("C:\\Program Files\\Git\\bin\\bash.exe", "gitbash"),
            Pair("C:\\Program Files (x86)\\Git\\bin\\bash.exe", "gitbash"),
            Pair("C:\\Windows\\System32\\bash.exe", "wsl"),
            Pair("C:\\msys64\\usr\\bin\\bash.exe", "msys2"),
            Pair("C:\\msys32\\usr\\bin\\bash.exe", "msys2")
        ))

        for ((path, type) in bashPaths) {
            if (File(path).exists()) return ShellInfo(path, true, true, type)
        }
        return ShellInfo("", true, false, "none", ShellState.NO_BASH)
    }

    fun verifyShell(callback: ((Boolean) -> Unit)? = null) {
        if (!shellInfo.hasBash) {
            shellInfo = shellInfo.copy(state = ShellState.NO_BASH, verificationError = "No bash shell found")
            notifyShellStateChange()
            callback?.invoke(false)
            return
        }
        if (shellInfo.state == ShellState.READY) { callback?.invoke(true); return }
        if (verificationInProgress) return

        verificationInProgress = true
        shellInfo = shellInfo.copy(state = ShellState.VERIFYING)
        notifyShellStateChange()

        ApplicationManager.getApplication().executeOnPooledThread {
            try {
                val result = runCommandSync(shellInfo.shellPath, listOf("--version"))
                val verified = result.first == 0 && result.second.lowercase().contains("bash")
                shellInfo = if (verified) {
                    log.info("Shell verified: ${result.second.lines().firstOrNull()}")
                    shellInfo.copy(state = ShellState.READY, verificationError = null)
                } else {
                    log.warn("Shell verification failed: output did not contain 'bash'")
                    shellInfo.copy(state = ShellState.SHELL_ERROR, verificationError = "Not a bash shell")
                }
            } catch (e: Exception) {
                log.warn("Shell verification exception", e)
                shellInfo = shellInfo.copy(state = ShellState.SHELL_ERROR, verificationError = "Execution failed: ${e.message}")
            } finally {
                verificationInProgress = false
                notifyShellStateChange()
                callback?.invoke(shellInfo.state == ShellState.READY)
            }
        }
    }

    fun reverifyShell(callback: ((Boolean) -> Unit)? = null) {
        shellInfo = detectShell()
        verificationInProgress = false
        verifyShell(callback)
    }

    fun canExecute(): Triple<Boolean, String?, ShellState> = when (shellInfo.state) {
        ShellState.NO_BASH -> Triple(false, "QonQrete requires bash. On Windows, install Git Bash or use WSL.", ShellState.NO_BASH)
        ShellState.VERIFYING -> Triple(false, "Shell verification in progress...", ShellState.VERIFYING)
        ShellState.SHELL_ERROR -> Triple(false, "Shell verification failed: ${shellInfo.verificationError}", ShellState.SHELL_ERROR)
        ShellState.READY -> Triple(true, null, ShellState.READY)
    }

    // ========================================================================
    // STATE & CALLBACKS
    // ========================================================================

    fun getShellInfo(): ShellInfo = shellInfo.copy()
    fun getRunStatus(): RunStatus = runStatus.get()
    
    fun onRunStateChange(callback: RunStateChangeCallback) { runStateCallbacks.add(callback) }
    fun removeRunStateChangeListener(callback: RunStateChangeCallback) { runStateCallbacks.remove(callback) }
    fun onShellStateChange(callback: ShellStateChangeCallback) { shellStateCallbacks.add(callback) }
    fun onRefresh(callback: RefreshCallback) { refreshCallbacks.add(callback) }
    fun removeRefreshListener(callback: RefreshCallback) { refreshCallbacks.remove(callback) }

    private fun notifyShellStateChange() {
        ApplicationManager.getApplication().invokeLater { shellStateCallbacks.forEach { it(shellInfo) } }
    }
    
    private fun updateRunStatus(status: RunStatus) {
        val previousState = runStatus.get().state
        runStatus.set(status)
        ApplicationManager.getApplication().invokeLater { 
            runStateCallbacks.forEach { it(status) }
            if (previousState == RunState.RUNNING && status.state in listOf(RunState.COMPLETED, RunState.FAILED, RunState.TIMEOUT)) {
                triggerRefresh()
            }
        }
    }
    
    private fun triggerRefresh() {
        ApplicationManager.getApplication().invokeLater { refreshCallbacks.forEach { it() } }
    }

    // ========================================================================
    // VALIDATION UTILITIES
    // ========================================================================

    fun sanitizeQonstructionName(name: String): SanitizeResult = QonQreteValidation.sanitizeQonstructionName(name)
    fun parseQageTimestamp(qageName: String): Long? = QonQreteValidation.parseQageTimestamp(qageName)
    fun formatQageTimestamp(qageName: String): String = QonQreteValidation.formatQageTimestamp(qageName)

    // ========================================================================
    // PATH DISCOVERY
    // ========================================================================

    fun findAllQonQretePaths(): List<String> {
        val settings = QonQreteSettingsState.getInstance()
        val paths = mutableListOf<String>()
        
        if (settings.customQonqretePath.isNotEmpty()) {
            val customPath = File(settings.customQonqretePath)
            if (customPath.exists() && customPath.name == "qonqrete.sh") {
                paths.add(customPath.absolutePath)
            }
        }
        
        val basePath = project.basePath ?: return paths
        
        // NEW: .qonqrete workspace-local deployment (preferred)
        val qonqreteDotPath = "$basePath/.qonqrete/qonqrete.sh"
        if (File(qonqreteDotPath).exists() && qonqreteDotPath !in paths) paths.add(qonqreteDotPath)
        
        val directPath = "$basePath/qonqrete.sh"
        if (File(directPath).exists() && directPath !in paths) paths.add(directPath)
        
        val contentRoots = ProjectRootManager.getInstance(project).contentRoots
        for (root in contentRoots) {
            listOf(
                "${root.path}/.qonqrete/qonqrete.sh",
                "${root.path}/qonqrete.sh",
                "${root.path}/qonqrete/qonqrete.sh"
            ).forEach { path ->
                if (File(path).exists() && path !in paths) paths.add(path)
            }
        }
        
        var current = File(basePath)
        repeat(3) {
            val checkPath = File(current, "qonqrete.sh")
            if (checkPath.exists() && checkPath.absolutePath !in paths) paths.add(checkPath.absolutePath)
            current = current.parentFile ?: return@repeat
        }
        
        return paths.distinct()
    }

    fun getQonQretePath(): String? {
        persistedQonqretePath?.let { if (File(it).exists()) return it; persistedQonqretePath = null }
        
        val settings = QonQreteSettingsState.getInstance()
        if (settings.customQonqretePath.isNotEmpty() && File(settings.customQonqretePath).exists()) {
            persistedQonqretePath = settings.customQonqretePath
            return settings.customQonqretePath
        }
        
        val allPaths = findAllQonQretePaths()
        return when {
            allPaths.isEmpty() -> null
            allPaths.size == 1 -> { persistedQonqretePath = allPaths.first(); allPaths.first() }
            else -> {
                val basePath = project.basePath ?: ""
                val baseDepth = File(basePath).absolutePath.count { it == File.separatorChar }
                val sorted = allPaths.sortedBy { path ->
                    kotlin.math.abs(File(path).absolutePath.count { it == File.separatorChar } - baseDepth)
                }
                log.info("Multiple QonQrete paths, selecting: ${sorted.first()}")
                persistedQonqretePath = sorted.first()
                sorted.first()
            }
        }
    }

    fun resolveQonQretePathWithPrompt(): String? {
        val allPaths = findAllQonQretePaths()
        when {
            allPaths.isEmpty() -> return null
            allPaths.size == 1 -> { persistedQonqretePath = allPaths.first(); return allPaths.first() }
            else -> {
                val selected = Messages.showEditableChooseDialog(
                    "Multiple QonQrete installations found.\nSelect which one to use:",
                    "Select QonQrete Root", Messages.getQuestionIcon(),
                    allPaths.toTypedArray(), allPaths.first(), null
                )
                if (selected != null && selected in allPaths) {
                    persistedQonqretePath = selected
                    return selected
                }
                return null
            }
        }
    }

    fun clearPathCache() { persistedQonqretePath = null; cachedVersion = null }
    fun getQonQreteWorkingDir(): String? = getQonQretePath()?.let { File(it).parent }

    fun hasTasqFile(): Boolean {
        // Check workspace root first (new canonical location)
        val rootTasq = getRootTasqPath()
        if (rootTasq != null && File(rootTasq).exists()) return true
        // Fallback: internal worqspace tasq
        return getQonQreteWorkingDir()?.let { File(it, "worqspace/tasq.md").exists() } ?: false
    }

    fun getTasqPath(): String? {
        // Prefer workspace root tasq.md
        val rootTasq = getRootTasqPath()
        if (rootTasq != null && File(rootTasq).exists()) return rootTasq
        // Fallback: internal worqspace tasq
        return getQonQreteWorkingDir()?.let { "$it/worqspace/tasq.md" }
    }

    fun getRootTasqPath(): String? {
        val basePath = project.basePath ?: return null
        return "$basePath/tasq.md"
    }

    fun getInternalTasqPath(): String? {
        return getQonQreteWorkingDir()?.let { "$it/worqspace/tasq.md" }
    }

    fun isDeployed(): Boolean {
        val basePath = project.basePath ?: return false
        return File(basePath, ".qonqrete/qonqrete.sh").exists()
    }

    fun syncRootTasqToInternal(): Boolean {
        val rootTasq = getRootTasqPath() ?: return false
        val internalTasq = getInternalTasqPath() ?: return false
        val rootFile = File(rootTasq)
        if (!rootFile.exists()) return false
        try {
            val worqspaceDir = File(internalTasq).parentFile
            if (!worqspaceDir.exists()) worqspaceDir.mkdirs()
            rootFile.copyTo(File(internalTasq), overwrite = true)
            log.info("Synced tasq.md → .qonqrete/worqspace/tasq.md")
            return true
        } catch (e: Exception) {
            log.warn("Failed to sync tasq: ${e.message}")
            return false
        }
    }

    fun ensureGitignore() {
        val basePath = project.basePath ?: return
        val gitignorePath = File(basePath, ".gitignore")
        val entry = ".qonqrete/"
        try {
            if (gitignorePath.exists()) {
                val content = gitignorePath.readText()
                if (!content.lines().any { it.trim() == entry || it.trim() == ".qonqrete" }) {
                    gitignorePath.appendText("\n# QonQrete runtime\n$entry\n")
                    log.info("Added .qonqrete/ to .gitignore")
                }
            } else {
                gitignorePath.writeText("# QonQrete runtime\n$entry\n")
                log.info("Created .gitignore with .qonqrete/")
            }
        } catch (e: Exception) {
            log.warn("Could not update .gitignore: ${e.message}")
        }
    }

    // ========================================================================
    // STATUS CHECKS
    // ========================================================================

    fun isInitialized(): InitStatus {
        val scriptPath = getQonQretePath() ?: return InitStatus(false, false, null)
        val workingDir = File(scriptPath).parent
        if (!File(workingDir, "Dockerfile").exists()) return InitStatus(false, false, null)
        
        // Check versioned image first, then legacy
        val version = getVersion()
        val imageNames = listOfNotNull(
            version?.let { "qonqrete-qage:$it" },
            "qonqrete-qage:latest",
            "qonqrete-qage"
        )
        
        for (engine in listOf("docker", "podman")) {
            for (imageName in imageNames) {
                try {
                    val result = runCommandSync(engine, listOf("image", "inspect", imageName))
                    if (result.first == 0) return InitStatus(true, true, engine)
                } catch (_: Exception) {}
            }
        }
        return InitStatus(true, false, null)
    }

    fun getVersion(): String? {
        cachedVersion?.let { return it }
        val workingDir = getQonQreteWorkingDir() ?: return null
        return try { 
            cachedVersion = File(workingDir, "VERSION").readText().trim()
            cachedVersion
        } catch (_: Exception) { null }
    }

    // ========================================================================
    // QAGE MANAGEMENT
    // ========================================================================

    fun getAvailableQages(): List<String> {
        val workingDir = getQonQreteWorkingDir() ?: return emptyList()
        val worqspacePath = File(workingDir, "worqspace")
        if (!worqspacePath.exists()) return emptyList()
        
        val settings = QonQreteSettingsState.getInstance()
        return try {
            worqspacePath.listFiles { file ->
                file.isDirectory && QonQreteValidation.isValidQageName(file.name)
            }?.map { QageInfo(it.name, parseQageTimestamp(it.name)) }
                ?.sortedByDescending { it.timestamp ?: 0L }
                ?.map { it.name }
                ?.take(settings.qageListLimit)
                ?: emptyList()
        } catch (e: Exception) { emptyList() }
    }

    private data class QageInfo(val name: String, val timestamp: Long?)

    fun getQageDetails(qageName: String): QageDetails? {
        if (!QonQreteValidation.isValidQageName(qageName)) return null
        val workingDir = getQonQreteWorkingDir() ?: return null
        val qagePath = File(workingDir, "worqspace/$qageName")
        if (!qagePath.exists()) return null
        
        fun listDir(subdir: String): List<String> {
            val dir = if (subdir.isEmpty()) qagePath else File(qagePath, subdir)
            return if (dir.exists() && dir.isDirectory) {
                dir.listFiles()?.filter { it.isFile }?.map { it.name }?.sorted() ?: emptyList()
            } else emptyList()
        }
        
        return QageDetails(
            name = qageName, path = qagePath.absolutePath, timestamp = parseQageTimestamp(qageName),
            artifacts = QageArtifacts(
                qodeyard = listDir("qodeyard"), exeq = listDir("exeq.d"),
                reqap = listDir("reqap.d"), briqs = listDir("briq.d"), bloqs = listDir("bloq.d")
            ),
            configFiles = listDir("").filter { it.endsWith(".yaml") || it.endsWith(".md") }
        )
    }

    fun getArtifactPath(qageName: String, category: String, fileName: String): String? {
        val workingDir = getQonQreteWorkingDir() ?: return null
        val subPath = if (category.isEmpty()) fileName else "$category/$fileName"
        val path = File(workingDir, "worqspace/$qageName/$subPath")
        return if (path.exists()) path.absolutePath else null
    }

    // ========================================================================
    // COMMAND EXECUTION
    // ========================================================================

    private fun runCommandSync(command: String, args: List<String>): Pair<Int, String> {
        val commandLine = GeneralCommandLine(listOf(command) + args)
        commandLine.withParentEnvironmentType(GeneralCommandLine.ParentEnvironmentType.CONSOLE)
        val handler = OSProcessHandler(commandLine)
        val output = StringBuilder()
        handler.addProcessListener(object : ProcessAdapter() {
            override fun onTextAvailable(event: ProcessEvent, outputType: Key<*>) { output.append(event.text) }
        })
        handler.startNotify()
        handler.waitFor(30000)
        return Pair(handler.exitCode ?: 1, output.toString())
    }

    private fun createMarkerPath(workingDir: String): Path =
        Path.of(workingDir, "worqspace", ".qonqrete_run_${System.currentTimeMillis()}.marker")

    private fun executeWithVerifiedBash(workingDir: String, command: String, description: String) {
        if (shellInfo.state != ShellState.READY) throw IllegalStateException("Shell not verified: ${shellInfo.state}")

        val markerPath = createMarkerPath(workingDir)
        currentMarkerPath = markerPath

        // SECURE: Write API keys to temp file, source + delete in command (never in scrollback)
        val envFile = writeTempEnvFile(workingDir)
        val envPrefix = if (envFile != null) {
            val envPath = ShellEscape.toUnixPath(envFile.absolutePath, shellInfo.isWindows)
            "source ${ShellEscape.escape(envPath)} && rm -f ${ShellEscape.escape(envPath)} && "
        } else ""
        val fullCommand = "$envPrefix$command"

        val bashScript = CommandBuilder.buildBashScript(workingDir, fullCommand, markerPath.toString(), null, shellInfo.isWindows)
        updateRunStatus(RunStatus(state = RunState.RUNNING, startTime = System.currentTimeMillis(), command = command))
        startMarkerWatch(markerPath)

        val settings = QonQreteSettingsState.getInstance()
        if (settings.autoOpenToolWindowOnRun) {
            ApplicationManager.getApplication().invokeLater {
                ToolWindowManager.getInstance(project).getToolWindow("QonQrete")?.show()
            }
        }

        ApplicationManager.getApplication().invokeLater {
            try {
                val terminalManager = TerminalToolWindowManager.getInstance(project)
                val terminalWidget = terminalManager.createLocalShellWidget(workingDir, TERMINAL_NAME, true)
                val bashWrappedCommand = CommandBuilder.wrapForBash(shellInfo.shellPath, bashScript)
                log.info("$description: $command")
                terminalWidget.executeCommand(bashWrappedCommand)
            } catch (e: Exception) {
                log.error("Failed to execute in terminal", e)
                updateRunStatus(RunStatus(state = RunState.FAILED, error = e.message, endTime = System.currentTimeMillis()))
            }
        }
    }

    /**
     * Write stored API keys (from PasswordSafe) to a temporary env file.
     * Only includes keys NOT already in process environment (env takes precedence).
     * Returns the file, or null if no keys need injection.
     */
    private fun writeTempEnvFile(workingDir: String): java.io.File? {
        val lines = mutableListOf<String>()
        val allKeys = listOf(
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENROUTER_API_KEY",
            "GOOGLE_API_KEY",
            "DEEPSEEK_API_KEY",
            "QWEN_API_KEY"
        )
        for (envKey in allKeys) {
            // Skip if already in real environment
            if (!System.getenv(envKey).isNullOrEmpty()) continue
            // Gemini/Google equivalence: skip GOOGLE if GEMINI already in env (and vice versa)
            if (envKey == "GOOGLE_API_KEY" && !System.getenv("GEMINI_API_KEY").isNullOrEmpty()) continue

            // Try stored secret, with Gemini/Google fallback
            var stored = sh.qonqrete.intellij.actions.SetAIConfigAction.getApiKey(envKey)
            if (stored.isNullOrEmpty() && envKey == "GOOGLE_API_KEY") {
                stored = sh.qonqrete.intellij.actions.SetAIConfigAction.getApiKey("GEMINI_API_KEY")
            }

            if (!stored.isNullOrEmpty()) {
                val escaped = stored.replace("'", "'\\''")
                lines.add("export $envKey='$escaped'")
                // Double-map Google → Gemini
                if (envKey == "GOOGLE_API_KEY") {
                    lines.add("export GEMINI_API_KEY='$escaped'")
                }
            }
        }
        if (lines.isEmpty()) return null

        val envFile = java.io.File(workingDir, ".qonqrete_env_${System.currentTimeMillis()}.tmp")
        envFile.writeText(lines.joinToString("\n") + "\n")
        // Restrict to owner-only read/write (chmod 600)
        envFile.setReadable(false, false)
        envFile.setReadable(true, true)
        envFile.setWritable(false, false)
        envFile.setWritable(true, true)
        envFile.setExecutable(false, false)
        envFile.deleteOnExit() // safety net — JVM removes on exit
        return envFile
    }

    private fun startMarkerWatch(markerPath: Path) {
        markerWatcherActive = false
        markerWatcherThread?.interrupt()
        
        markerWatcherActive = true
        val settings = QonQreteSettingsState.getInstance()
        val timeoutMs = settings.markerTimeoutMinutes * 60 * 1000L
        
        markerWatcherThread = Thread({
            val startTime = System.currentTimeMillis()
            while (markerWatcherActive && !Thread.currentThread().isInterrupted) {
                try { Thread.sleep(1000) } catch (_: InterruptedException) { break }
                if (Files.exists(markerPath)) { handleMarkerFileDetected(markerPath.toString()); break }
                if (System.currentTimeMillis() - startTime > timeoutMs) {
                    updateRunStatus(RunStatus(state = RunState.TIMEOUT, endTime = System.currentTimeMillis(), error = "Timeout"))
                    markerWatcherActive = false
                    break
                }
            }
        }, "QonQrete-MarkerWatcher").apply { isDaemon = true; start() }
    }

    private fun handleMarkerFileDetected(path: String) {
        if (runStatus.get().state != RunState.RUNNING) return
        markerWatcherActive = false
        try { Thread.sleep(100) } catch (_: InterruptedException) {}
        try {
            val markerFile = File(path)
            if (markerFile.exists()) {
                val exitCode = markerFile.readText().trim().toIntOrNull()
                updateRunStatus(RunStatus(
                    state = if (exitCode == 0) RunState.COMPLETED else RunState.FAILED,
                    exitCode = exitCode, endTime = System.currentTimeMillis()
                ))
                try { markerFile.delete() } catch (_: Exception) {}
            }
        } catch (_: Exception) {}
    }

    // ========================================================================
    // CLEANUP
    // ========================================================================

    fun cleanupOrphanedBackups() {
        val workingDir = getQonQreteWorkingDir() ?: return
        val worqspacePath = File(workingDir, "worqspace")
        val backupPath = File(worqspacePath, ".tasq.md.qonqrete-backup")
        val tasqPath = File(worqspacePath, "tasq.md")

        if (backupPath.exists()) {
            log.info("Found orphaned backup: ${backupPath.absolutePath}")
            try {
                if (tasqPath.exists()) {
                    if (backupPath.readText() != tasqPath.readText()) {
                        backupPath.copyTo(tasqPath, overwrite = true)
                        notify("QonQrete", "Restored tasq.md from orphaned backup", NotificationType.WARNING)
                    }
                } else { backupPath.copyTo(tasqPath) }
                backupPath.delete()
            } catch (e: Exception) { log.warn("Could not clean up backup", e) }
        }
        try {
            worqspacePath.listFiles()?.filter { it.name.startsWith(".qonqrete_run_") && it.name.endsWith(".marker") }
                ?.forEach { it.delete() }
        } catch (_: Exception) {}
    }

    // ========================================================================
    // PUBLIC COMMANDS
    // ========================================================================

    fun init() {
        val scriptPath = getQonQretePath() ?: throw IllegalStateException("QonQrete script not found")
        executeWithVerifiedBash(File(scriptPath).parent, CommandBuilder.qonqrete().init().build(), "Building container image")
    }

    fun run(config: QonQreteRunConfig) {
        val scriptPath = getQonQretePath() ?: throw IllegalStateException("QonQrete script not found")
        executeWithVerifiedBash(File(scriptPath).parent, CommandBuilder.qonqrete().run(config).build(), "Running QonQrete")
    }

    fun runWithFile(filePath: String, config: QonQreteRunConfig) {
        if (shellInfo.state != ShellState.READY) throw IllegalStateException("Shell not verified")
        val scriptPath = getQonQretePath() ?: throw IllegalStateException("QonQrete script not found")
        val workingDir = File(scriptPath).parent
        val worqspaceTasq = File(workingDir, "worqspace/tasq.md")
        val backupPath = File(workingDir, "worqspace/.tasq.md.qonqrete-backup")

        var hadOriginal = false
        if (worqspaceTasq.exists()) { worqspaceTasq.copyTo(backupPath, overwrite = true); hadOriginal = true }
        File(filePath).copyTo(worqspaceTasq, overwrite = true)

        val markerPath = createMarkerPath(workingDir)
        currentMarkerPath = markerPath
        
        val runCommand = CommandBuilder.qonqrete().run(config).build()
        // SECURE: use temp env file for API keys (never in command text)
        val envFile = writeTempEnvFile(workingDir)
        val envPrefix = if (envFile != null) {
            val envPath = ShellEscape.toUnixPath(envFile.absolutePath, shellInfo.isWindows)
            "source ${ShellEscape.escape(envPath)} && rm -f ${ShellEscape.escape(envPath)} && "
        } else ""
        val fullRunCommand = "$envPrefix$runCommand"
        val restoreCommand = CommandBuilder.buildRestoreCommand(backupPath.absolutePath, worqspaceTasq.absolutePath, hadOriginal, shellInfo.isWindows)
        val bashScript = CommandBuilder.buildBashScript(workingDir, fullRunCommand, markerPath.toString(), restoreCommand, shellInfo.isWindows)

        updateRunStatus(RunStatus(state = RunState.RUNNING, startTime = System.currentTimeMillis(), command = runCommand))
        startMarkerWatch(markerPath)

        val settings = QonQreteSettingsState.getInstance()
        if (settings.autoOpenToolWindowOnRun) {
            ApplicationManager.getApplication().invokeLater {
                ToolWindowManager.getInstance(project).getToolWindow("QonQrete")?.show()
            }
        }

        ApplicationManager.getApplication().invokeLater {
            try {
                val terminalManager = TerminalToolWindowManager.getInstance(project)
                val terminalWidget = terminalManager.createLocalShellWidget(workingDir, TERMINAL_NAME, true)
                terminalWidget.executeCommand(CommandBuilder.wrapForBash(shellInfo.shellPath, bashScript))
            } catch (e: Exception) {
                updateRunStatus(RunStatus(state = RunState.FAILED, error = e.message, endTime = System.currentTimeMillis()))
            }
        }
    }

    fun resume(qageName: String? = null, config: QonQreteRunConfig? = null) {
        val scriptPath = getQonQretePath() ?: throw IllegalStateException("QonQrete script not found")
        executeWithVerifiedBash(File(scriptPath).parent, CommandBuilder.qonqrete().resume(qageName, config).build(), "Resuming")
    }

    fun clean(qageName: String? = null, cleanAll: Boolean = false) {
        val scriptPath = getQonQretePath() ?: throw IllegalStateException("QonQrete script not found")
        executeWithVerifiedBash(File(scriptPath).parent, CommandBuilder.qonqrete().clean(qageName, cleanAll).build(), "Cleaning")
    }

    fun notify(title: String, content: String, type: NotificationType = NotificationType.INFORMATION) {
        NotificationGroupManager.getInstance().getNotificationGroup("QonQrete Notifications")
            .createNotification(title, content, type).notify(project)
    }

    override fun dispose() { 
        markerWatcherActive = false 
        markerWatcherThread?.interrupt()
        runStateCallbacks.clear()
        shellStateCallbacks.clear()
        refreshCallbacks.clear()
    }
}
