/**
 * Init Workspace Action
 * Initialize QonQrete container image
 *
 * @author WoNQ
 * @version VERSION
 * @license Apache-2.0
 */

package sh.qonqrete.intellij.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ui.Messages
import sh.qonqrete.intellij.services.*

class InitWorkspaceAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = QonQreteProjectService.getInstance(project)

        // Check shell state
        val (canRun, reason, state) = service.canExecute()
        if (!canRun) {
            when (state) {
                ShellState.VERIFYING -> {
                    service.notify("QonQrete", "Please wait - shell verification in progress...", NotificationType.WARNING)
                }
                ShellState.NO_BASH -> {
                    Messages.showErrorDialog(project, reason, "QonQrete: No Bash Shell")
                }
                ShellState.SHELL_ERROR -> {
                    Messages.showErrorDialog(project, reason, "QonQrete: Shell Error")
                }
                else -> {}
            }
            return
        }

        // Check if QonQrete is available
        if (service.getQonQretePath() == null) {
            Messages.showErrorDialog(
                project,
                "Could not find qonqrete.sh in this project.",
                "QonQrete Not Found"
            )
            return
        }

        // Check current init status
        val initStatus = service.isInitialized()

        if (initStatus.hasImage) {
            val rebuild = Messages.showYesNoDialog(
                project,
                "QonQrete container image already exists (using ${initStatus.engine}).\n\n" +
                "Would you like to rebuild it?",
                "QonQrete: Already Initialized",
                Messages.getQuestionIcon()
            )
            if (rebuild != Messages.YES) {
                return
            }
        }

        // Execute init
        try {
            service.init()
            service.notify("QonQrete", "Building container image...", NotificationType.INFORMATION)
        } catch (ex: Exception) {
            service.notify("QonQrete Error", "Failed to init: ${ex.message}", NotificationType.ERROR)
        }
    }

    override fun update(e: AnActionEvent) {
        val project = e.project
        val presentation = e.presentation

        if (project == null) {
            presentation.isEnabledAndVisible = false
            return
        }

        val service = QonQreteProjectService.getInstance(project)
        val hasQonqrete = service.getQonQretePath() != null
        val (canRun, _, _) = service.canExecute()
        val isRunning = service.getRunStatus().state == RunState.RUNNING

        presentation.isVisible = hasQonqrete
        presentation.isEnabled = hasQonqrete && canRun && !isRunning
    }
}
