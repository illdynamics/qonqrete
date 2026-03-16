/**
 * Open Config Dialog Action
 * Open the full run configuration dialog
 *
 * @author WoNQ
 * @version 1.1.9
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.ui.Messages
import sh.qonqrete.intellij.services.*
import sh.qonqrete.intellij.ui.QonQreteConfigDialog

class OpenConfigDialogAction : AnAction() {

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

        // Check if tasq.md exists
        if (!service.hasTasqFile()) {
            Messages.showErrorDialog(
                project,
                "No tasq.md found in worqspace/.\n\nCreate a tasq.md file first.",
                "QonQrete: No Tasq File"
            )
            return
        }

        // Show full config dialog
        val dialog = QonQreteConfigDialog(project, service)
        if (dialog.showAndGet()) {
            val config = dialog.getConfig()

            // Save all documents before running
            FileDocumentManager.getInstance().saveAllDocuments()

            try {
                service.run(config)
            } catch (ex: Exception) {
                service.notify("QonQrete Error", "Failed to start: ${ex.message}", NotificationType.ERROR)
            }
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
