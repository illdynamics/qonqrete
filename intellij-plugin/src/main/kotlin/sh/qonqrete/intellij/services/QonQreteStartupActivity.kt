/**
 * QonQrete Startup Activity
 * Handles plugin initialization on project open
 * Non-blocking startup - never shows modal dialogs from startup
 *
 * @author WoNQ
 * @version VERSION
 * @license Apache-2.0
 */

package sh.qonqrete.intellij.services

import com.intellij.notification.NotificationType
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity

class QonQreteStartupActivity : ProjectActivity {

    private val log = Logger.getInstance(QonQreteStartupActivity::class.java)

    override suspend fun execute(project: Project) {
        log.info("QonQrete startup activity executing for project: ${project.name}")

        val service = QonQreteProjectService.getInstance(project)

        // 1. Clean up any orphaned backups from previous sessions
        try {
            service.cleanupOrphanedBackups()
        } catch (e: Exception) {
            log.warn("Error during orphan cleanup", e)
        }

        // 2. Start shell verification (non-blocking)
        service.verifyShell { verified ->
            if (!verified) {
                val shellInfo = service.getShellInfo()
                when (shellInfo.state) {
                    ShellState.NO_BASH -> {
                        service.notify(
                            "QonQrete: No Bash Shell",
                            "QonQrete requires a bash shell. On Windows, please install Git Bash or use WSL.",
                            NotificationType.WARNING
                        )
                    }
                    ShellState.SHELL_ERROR -> {
                        service.notify(
                            "QonQrete: Shell Error",
                            "Shell verification failed: ${shellInfo.verificationError}",
                            NotificationType.WARNING
                        )
                    }
                    else -> {}
                }
            }
        }

        val settings = QonQreteSettingsState.getInstance()
        if (!service.isDeployed()) {
            // Non-blocking startup: use a notification with an action instead of a
            // modal dialog to avoid blocking the event dispatch thread during IDE
            // initialization (which caused a 10-minute timeout in verification tests).
            service.notify(
                "QonQrete: Setup Required",
                "Deploy QonQrete to this workspace and configure your AI provider.",
                NotificationType.INFORMATION
            )
        } else if (!settings.welcomeShown && service.getQonQretePath() != null) {
            ApplicationManager.getApplication().invokeLater {
                val version = service.getVersion() ?: "unknown"
                service.notify(
                    "QonQrete Ready",
                    "QonQrete v$version detected. Use Tools → QonQrete or Ctrl+Alt+Q to run.",
                    NotificationType.INFORMATION
                )
                settings.welcomeShown = true
            }
        }

        log.info("QonQrete startup activity completed")
    }
}
