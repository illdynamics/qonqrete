/**
 * QonQrete Startup Activity
 * Handles plugin initialization on project open
 *
 * @author WoNQ
 * @version 1.1.9
 * @license AGPL-3.0
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

        // 2. Start shell verification
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

        // 3. Show welcome notification on first run
        val settings = QonQreteSettingsState.getInstance()
        if (!settings.welcomeShown && service.getQonQretePath() != null) {
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
