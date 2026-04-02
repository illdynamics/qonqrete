/**
 * Deploy to Workspace Action
 * Downloads and extracts QonQrete runtime into <project>/.qonqrete/
 *
 * @author WoNQ
 * @version 1.2.0
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.extensions.PluginId
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.ide.plugins.PluginManagerCore
import sh.qonqrete.intellij.services.QonQreteProjectService
import sh.qonqrete.intellij.services.RunState
import java.io.*
import java.net.HttpURLConnection
import java.net.URL
import java.util.zip.ZipInputStream

class DeployToWorkspaceAction : AnAction() {

    companion object {
        private const val GITHUB_RELEASE_BASE = "https://github.com/illdynamics/qonqrete/releases/download"
        private const val PLUGIN_ID = "sh.qonqrete"
        private val log = Logger.getInstance(DeployToWorkspaceAction::class.java)

        /**
         * Resolve runtime version from single source of truth.
         *
         * Priority:
         *   1. <project>/.qonqrete/VERSION  (if runtime already deployed)
         *   2. Plugin's own version from PluginManagerCore
         *   3. "latest" as ultimate fallback
         */
        fun resolveRuntimeVersion(project: Project): String {
            val basePath = project.basePath

            // 1. Try deployed VERSION file
            if (basePath != null) {
                try {
                    val versionFile = File(basePath, ".qonqrete/VERSION")
                    if (versionFile.exists()) {
                        val v = versionFile.readText().trim().removePrefix("v").removePrefix("V")
                        if (v.isNotEmpty() && v.matches(Regex("^\\d+\\.\\d+.*"))) {
                            log.info("Resolved runtime version from VERSION file: $v")
                            return v
                        }
                    }
                } catch (e: Exception) {
                    log.warn("Could not read .qonqrete/VERSION: ${e.message}")
                }
            }

            // 2. Plugin version
            try {
                val pluginId = PluginId.getId(PLUGIN_ID)
                val descriptor = PluginManagerCore.getPlugin(pluginId)
                if (descriptor != null) {
                    val v = descriptor.version.trim().removePrefix("v").removePrefix("V")
                    if (v.isNotEmpty() && v.matches(Regex("^\\d+\\.\\d+.*"))) {
                        log.info("Resolved runtime version from plugin version: $v")
                        return v
                    }
                }
            } catch (e: Exception) {
                log.warn("Could not read plugin version: ${e.message}")
            }

            // 3. Fallback
            log.warn("Could not resolve runtime version, falling back to 'latest'")
            return "latest"
        }
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = QonQreteProjectService.getInstance(project)
        val basePath = project.basePath

        if (basePath == null) {
            Messages.showErrorDialog(project, "No project directory found.", "QonQrete: Deploy")
            return
        }

        val qonqreteDir = File(basePath, ".qonqrete")

        // Check if already deployed
        if (File(qonqreteDir, "qonqrete.sh").exists()) {
            val choice = Messages.showDialog(
                project,
                "QonQrete runtime already deployed in this workspace.",
                "QonQrete: Deploy",
                arrayOf("Reinstall", "Cancel"),
                0,
                Messages.getQuestionIcon()
            )
            if (choice != 0) return
            qonqreteDir.deleteRecursively()
        }

        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "QonQrete: Deploying to Workspace", false) {
            override fun run(indicator: ProgressIndicator) {
                try {
                    // Resolve version dynamically
                    val version = resolveRuntimeVersion(project)

                    indicator.text = "Downloading runtime v$version..."
                    indicator.fraction = 0.1

                    val zipUrl = "$GITHUB_RELEASE_BASE/v$version/qonqrete-v$version.zip"
                    val tmpDir = File(basePath, ".qonqrete-tmp-${System.currentTimeMillis()}")
                    tmpDir.mkdirs()
                    val zipFile = File(tmpDir, "qonqrete.zip")

                    var downloaded = false
                    try {
                        downloadFile(zipUrl, zipFile)
                        downloaded = true
                    } catch (ex: Exception) {
                        // Fallback: try shallow git clone
                        indicator.text = "Zip download failed, trying git clone..."
                        try {
                            val pb = ProcessBuilder("git", "clone", "--depth", "1", "--branch", "v$version",
                                "https://github.com/illdynamics/qonqrete.git", qonqreteDir.absolutePath)
                            pb.redirectErrorStream(true)
                            val proc = pb.start()
                            proc.waitFor()
                            if (proc.exitValue() == 0) {
                                File(qonqreteDir, ".git").deleteRecursively()
                                downloaded = false // skip zip extraction
                            } else {
                                throw Exception("Git clone failed with exit code ${proc.exitValue()}")
                            }
                        } catch (gitEx: Exception) {
                            throw Exception("Download failed: $ex\nGit fallback also failed: $gitEx")
                        }
                    }

                    if (downloaded) {
                        indicator.text = "Extracting runtime..."
                        indicator.fraction = 0.4

                        qonqreteDir.mkdirs()
                        extractZip(zipFile, qonqreteDir)
                        flattenTopLevel(qonqreteDir)
                    }

                    tmpDir.deleteRecursively()

                    // Validate
                    indicator.text = "Validating..."
                    indicator.fraction = 0.7
                    val scriptFile = File(qonqreteDir, "qonqrete.sh")
                    if (!scriptFile.exists()) {
                        throw Exception("qonqrete.sh not found after extraction")
                    }
                    scriptFile.setExecutable(true)
                    File(qonqreteDir, "entrypoint.sh").takeIf { it.exists() }?.setExecutable(true)

                    // .gitignore
                    indicator.text = "Updating .gitignore..."
                    indicator.fraction = 0.85
                    service.ensureGitignore()

                    // Refresh
                    indicator.text = "Finalizing..."
                    indicator.fraction = 0.95
                    service.clearPathCache()

                    ApplicationManager.getApplication().invokeLater {
                        service.notify("QonQrete", "Runtime deployed successfully to .qonqrete/", NotificationType.INFORMATION)

                        // Offer to create tasq.md
                        val rootTasq = File(basePath, "tasq.md")
                        if (!rootTasq.exists()) {
                            val create = Messages.showYesNoDialog(
                                project,
                                "QonQrete deployed! Create a tasq.md to get started?",
                                "QonQrete: Deploy",
                                Messages.getQuestionIcon()
                            )
                            if (create == Messages.YES) {
                                com.intellij.openapi.actionSystem.ActionManager.getInstance()
                                    .getAction("QonQrete.CreateTasq")?.actionPerformed(e)
                            }
                        }

                        // Prompt for AI configuration
                        val configAI = Messages.showYesNoDialog(
                            project,
                            "Set up AI providers and API keys now?",
                            "QonQrete: AI Configuration",
                            Messages.getQuestionIcon()
                        )
                        if (configAI == Messages.YES) {
                            com.intellij.openapi.actionSystem.ActionManager.getInstance()
                                .getAction("QonQrete.SetAIConfig")?.actionPerformed(e)
                        }
                    }

                } catch (ex: Exception) {
                    ApplicationManager.getApplication().invokeLater {
                        service.notify("QonQrete Error", "Deploy failed: ${ex.message}", NotificationType.ERROR)
                    }
                }
            }
        })
    }

    private fun downloadFile(urlStr: String, dest: File) {
        var url = URL(urlStr)
        var redirects = 0
        while (redirects < 5) {
            val conn = url.openConnection() as HttpURLConnection
            conn.connectTimeout = 30000
            conn.readTimeout = 60000
            conn.instanceFollowRedirects = false
            val code = conn.responseCode
            if (code == HttpURLConnection.HTTP_MOVED_PERM || code == HttpURLConnection.HTTP_MOVED_TEMP || code == 307) {
                url = URL(conn.getHeaderField("Location"))
                redirects++
                conn.disconnect()
                continue
            }
            if (code != 200) {
                conn.disconnect()
                throw Exception("HTTP $code from $urlStr")
            }
            conn.inputStream.use { input -> FileOutputStream(dest).use { output -> input.copyTo(output) } }
            conn.disconnect()
            return
        }
        throw Exception("Too many redirects")
    }

    private fun extractZip(zipFile: File, destDir: File) {
        ZipInputStream(FileInputStream(zipFile)).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                val outFile = File(destDir, entry.name)
                if (entry.isDirectory) {
                    outFile.mkdirs()
                } else {
                    outFile.parentFile?.mkdirs()
                    FileOutputStream(outFile).use { fos -> zis.copyTo(fos) }
                }
                zis.closeEntry()
                entry = zis.nextEntry
            }
        }
    }

    private fun flattenTopLevel(dir: File) {
        val entries = dir.listFiles()?.filter { !it.name.startsWith("__MACOSX") && !it.name.startsWith(".") } ?: return
        if (entries.size == 1 && entries[0].isDirectory) {
            val inner = entries[0]
            inner.listFiles()?.forEach { f -> f.renameTo(File(dir, f.name)) }
            inner.deleteRecursively()
        }
        File(dir, "__MACOSX").takeIf { it.exists() }?.deleteRecursively()
    }

    override fun update(e: AnActionEvent) {
        val project = e.project
        e.presentation.isEnabledAndVisible = project != null &&
            project.basePath != null &&
            QonQreteProjectService.getInstance(project).getRunStatus().state != RunState.RUNNING
    }
}
