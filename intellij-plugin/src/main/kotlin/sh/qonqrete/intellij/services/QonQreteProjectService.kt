/**
 * QonQrete v2 project service.
 *
 * The v2 engine is the `qq` Python CLI. This service locates the binary and
 * executes QonQrete commands in an IntelliJ run console (PTY when available so
 * the TUI cockpit renders correctly).
 */
package sh.qonqrete.intellij.services

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessListener
import com.intellij.execution.process.ProcessEvent
import com.intellij.notification.NotificationGroupManager
import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.util.Key
import com.intellij.openapi.util.SystemInfo
import com.intellij.openapi.wm.ToolWindowManager
import java.io.File

@Service(Service.Level.PROJECT)
class QonQreteProjectService(private val project: Project) : Disposable {

    private val log = Logger.getInstance(QonQreteProjectService::class.java)

    companion object {
        private const val RUN_CONTENT_NAME = "QonQrete"
        @JvmStatic
        fun getInstance(project: Project): QonQreteProjectService {
            return project.getService(QonQreteProjectService::class.java)
        }
    }

    fun notify(title: String, content: String, type: NotificationType = NotificationType.INFORMATION) {
        NotificationGroupManager.getInstance().getNotificationGroup("QonQrete Notifications")
            .createNotification(title, content, type).notify(project)
    }

    /** Resolve the base command (executable + optional prefix). */
    fun qqCommand(): List<String> {
        val settings = QonQreteSettingsState.getInstance()
        if (settings.qqPath.isNotBlank()) {
            val p = File(settings.qqPath)
            if (p.exists()) return listOf(p.absolutePath)
        }
        // Prefer a local wrapper if present.
        val home = System.getProperty("user.home")
        val local = File(home, ".local/bin/qq")
        if (local.exists()) return listOf(local.absolutePath)
        return listOf("qq")
    }

    fun isAvailable(): Boolean {
        return try {
            val pb = ProcessBuilder(qqCommand() + listOf("--help"))
            pb.redirectErrorStream(true)
            val proc = pb.start()
            proc.inputStream.bufferedReader().readText()
            proc.waitFor() == 0
        } catch (_: Exception) { false }
    }

    private fun runCommandSync(command: String, args: List<String>, timeoutMs: Long = 30000): Pair<Int, String> {
        return try {
            val commandLine = GeneralCommandLine(listOf(command) + args)
            commandLine.withParentEnvironmentType(GeneralCommandLine.ParentEnvironmentType.CONSOLE)
            val handler = OSProcessHandler(commandLine)
            val output = StringBuilder()
            handler.addProcessListener(object : ProcessListener {
                override fun onTextAvailable(event: ProcessEvent, outputType: Key<*>) { output.append(event.text) }
            })
            handler.startNotify()
            handler.waitFor(timeoutMs)
            Pair(handler.exitCode ?: 1, output.toString())
        } catch (e: Exception) {
            Pair(1, e.message ?: "")
        }
    }

    private fun executeInConsole(command: List<String>, workingDir: String?, description: String) {
        ApplicationManager.getApplication().invokeLater {
            try {
                val cmdLine = com.intellij.execution.configurations.PtyCommandLine(command)
                if (workingDir != null) cmdLine.setWorkDirectory(workingDir)
                cmdLine.withCharset(Charsets.UTF_8)

                val handler = com.intellij.execution.process.KillableColoredProcessHandler(cmdLine)
                val consoleView = com.intellij.execution.impl.ConsoleViewImpl(project, true)
                consoleView.attachToProcess(handler)

                val descriptor = com.intellij.execution.ui.RunContentDescriptor(
                    consoleView, handler, consoleView.component, RUN_CONTENT_NAME
                )
                com.intellij.execution.ui.RunContentManager.getInstance(project).showRunContent(
                    com.intellij.execution.executors.DefaultRunExecutor.getRunExecutorInstance(),
                    descriptor
                )
                handler.startNotify()

                ToolWindowManager.getInstance(project).getToolWindow("QonQrete")?.show()
                log.info("$description: ${command.joinToString(" ")}")
            } catch (e: Exception) {
                log.error("Failed to execute QonQrete", e)
                notify("QonQrete", "Failed to start: ${e.message}", NotificationType.ERROR)
            }
        }
    }

    private fun baseWorkingDir(): String? = project.basePath

    fun runTask(config: QonQreteRunConfig) {
        val dest = File(config.destinationDir.ifBlank { project.basePath ?: "." }).absolutePath
        File(dest).mkdirs()
        val args = mutableListOf("run", config.taskFile, dest)
        if (config.noTui) args += "--no-tui"
        executeInConsole(qqCommand() + args, baseWorkingDir(), "Running QonQrete task")
    }

    fun runDoctor() = executeInConsole(qqCommand() + listOf("doctor"), baseWorkingDir(), "Running qq doctor")
    fun runVerify() = executeInConsole(qqCommand() + listOf("verify", "--skip-package-steps"), baseWorkingDir(), "Running qq verify")

    fun runCleanup(repoRoot: String) {
        executeInConsole(qqCommand() + listOf("cleanup", "--repo-root", File(repoRoot).absolutePath), baseWorkingDir(), "Running qq cleanup")
    }

    fun runReplay(eventsFile: String?) {
        val file = eventsFile ?: pickEventsFile() ?: return
        executeInConsole(qqCommand() + listOf("replay", file), baseWorkingDir(), "Running qq replay")
    }

    fun runRuns() = executeInConsole(qqCommand() + listOf("runs", "sessions"), baseWorkingDir(), "Listing QonQrete runs")

    fun runExec(command: String) = executeInConsole(qqCommand() + listOf("exec", command), baseWorkingDir(), "Running qq exec")

    fun runChat() = executeInConsole(qqCommand() + listOf("chat"), baseWorkingDir(), "Starting QonQrete chat")

    fun openConfig() {
        val config = sh.qonqrete.intellij.util.QonQreteConfig.configPath(project) ?: run {
            notify("QonQrete", "Config not found. Set configPath in Settings → Tools → QonQrete.", NotificationType.WARNING)
            return
        }
        val vf = com.intellij.openapi.vfs.LocalFileSystem.getInstance().refreshAndFindFileByPath(config)
        if (vf != null) {
            com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project).openFile(vf, true)
        } else {
            notify("QonQrete", "Could not open $config", NotificationType.ERROR)
        }
    }

    fun listRunsForPicker(): List<String> {
        return try {
            val base = qqCommand()
            val result = if (base.size == 1) runCommandSync(base[0], listOf("runs", "sessions", "--json"))
                         else runCommandSync(base[0], base.drop(1) + listOf("runs", "sessions", "--json"))
            if (result.first != 0) emptyList()
            else {
                // Parse the JSON with a simple extraction of "run_id" strings.
                val ids = mutableListOf<String>()
                val re = Regex("\"run_id\"\\s*:\\s*\"([^\"]+)\"")
                for (m in re.findAll(result.second)) ids.add(m.groupValues[1])
                ids.distinct()
            }
        } catch (_: Exception) { emptyList() }
    }

    private fun pickEventsFile(): String? {
        val descriptor = com.intellij.openapi.fileChooser.FileChooserDescriptor(true, false, false, false, false, false)
        descriptor.title = "Select a QonQrete events.jsonl file"
        descriptor.withFileFilter { file -> file.extension == "jsonl" }
        val chosen = com.intellij.openapi.fileChooser.FileChooser.chooseFile(descriptor, project, null)
        return chosen?.path
    }

    fun promptDestination(defaultDir: String): String? {
        val value = Messages.showInputDialog(
            project,
            "Destination directory for the QonQrete build:",
            "QonQrete Destination",
            Messages.getQuestionIcon(),
            defaultDir,
            null
        )
        return value?.takeIf { it.isNotBlank() }
    }

    override fun dispose() {}
}
