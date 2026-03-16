/**
 * Run Tasq Action
 * Execute QonQrete with canonical worqspace/tasq.md
 *
 * @author WoNQ
 * @version 1.1.9
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.ui.Messages
import sh.qonqrete.intellij.services.*
import sh.qonqrete.intellij.ui.QonQreteConfigDialog
import sh.qonqrete.intellij.ui.QonQreteQonstructionNameDialog

class RunTasqAction : AnAction() {

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
                    val retry = Messages.showYesNoDialog(
                        project,
                        "$reason\n\nWould you like to retry verification?",
                        "QonQrete: Shell Error",
                        Messages.getErrorIcon()
                    )
                    if (retry == Messages.YES) {
                        service.reverifyShell()
                    }
                }
                else -> {}
            }
            return
        }

        // Check if QonQrete is available
        if (service.getQonQretePath() == null) {
            Messages.showErrorDialog(
                project,
                "Could not find qonqrete.sh in this project.\n\nMake sure you have opened a QonQrete workspace.",
                "QonQrete Not Found"
            )
            return
        }

        // Check if tasq.md exists
        if (!service.hasTasqFile()) {
            Messages.showErrorDialog(
                project,
                "No tasq.md found in worqspace/.\n\nCreate a tasq.md file to define your build task.",
                "QonQrete: No Tasq File"
            )
            return
        }

        // Save all documents before running
        FileDocumentManager.getInstance().saveAllDocuments()

        // Get configuration
        val config = promptForConfig(project, service) ?: return

        // Execute
        try {
            service.run(config)
        } catch (ex: Exception) {
            service.notify("QonQrete Error", "Failed to start: ${ex.message}", NotificationType.ERROR)
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
        val hasTasq = service.hasTasqFile()
        val (canRun, _, state) = service.canExecute()
        val isRunning = service.getRunStatus().state == RunState.RUNNING

        presentation.isVisible = hasQonqrete
        presentation.isEnabled = hasQonqrete && hasTasq && canRun && !isRunning

        presentation.text = when {
            isRunning -> "QonQrete: Running..."
            state == ShellState.VERIFYING -> "QonQrete: Verifying Shell..."
            !hasTasq -> "QonQrete: No tasq.md"
            else -> "QonQrete: Run Tasq"
        }
    }

    private fun promptForConfig(project: com.intellij.openapi.project.Project, service: QonQreteProjectService): QonQreteRunConfig? {
        val settings = QonQreteSettingsState.getInstance()

        // Quick run with defaults, or show config dialog based on modifier keys
        val useQuickRun = true // Could check for shift key to show full dialog

        if (useQuickRun) {
            var config = QonQreteRunConfig.fromSettings()

            // Prompt for qonstruction name if not in autonomous mode
            if (!config.autonomous) {
                val nameDialog = QonQreteQonstructionNameDialog(project, service)
                if (!nameDialog.showAndGet()) {
                    return null
                }
                val name = nameDialog.getQonstructionName()
                if (name != null) {
                    config = config.copy(qonstructionName = name)
                }
            }

            return config
        } else {
            val dialog = QonQreteConfigDialog(project, service)
            if (dialog.showAndGet()) {
                return dialog.getConfig()
            }
            return null
        }
    }
}
