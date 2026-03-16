/**
 * Run As QonQrete Tasq Action
 * Execute a non-canonical markdown file as a temporary tasq
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
import java.io.File

class RunAsQonqreteTasqAction : AnAction() {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val virtualFile = e.getData(CommonDataKeys.VIRTUAL_FILE) ?: return
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

        val filePath = virtualFile.path

        // Confirm running non-canonical file
        val confirm = Messages.showYesNoDialog(
            project,
            "Run '${virtualFile.name}' as a QonQrete tasq?\n\n" +
            "This will temporarily replace worqspace/tasq.md and restore it after the run.",
            "Run as QonQrete Tasq",
            Messages.getQuestionIcon()
        )

        if (confirm != Messages.YES) {
            return
        }

        // Save all documents before running
        FileDocumentManager.getInstance().saveAllDocuments()

        // Get configuration
        var config = QonQreteRunConfig.fromSettings()

        // Prompt for qonstruction name if not in autonomous mode
        if (!config.autonomous) {
            val nameDialog = QonQreteQonstructionNameDialog(project, service)
            if (!nameDialog.showAndGet()) {
                return
            }
            val name = nameDialog.getQonstructionName()
            if (name != null) {
                config = config.copy(qonstructionName = name)
            }
        }

        // Execute with temp file
        try {
            service.runWithFile(filePath, config)
        } catch (ex: Exception) {
            service.notify("QonQrete Error", "Failed to start: ${ex.message}", NotificationType.ERROR)
        }
    }

    override fun update(e: AnActionEvent) {
        val project = e.project
        val virtualFile = e.getData(CommonDataKeys.VIRTUAL_FILE)
        val presentation = e.presentation

        if (project == null || virtualFile == null) {
            presentation.isEnabledAndVisible = false
            return
        }

        val service = QonQreteProjectService.getInstance(project)
        val hasQonqrete = service.getQonQretePath() != null
        val isMarkdown = virtualFile.extension?.lowercase() == "md"
        val (canRun, _, _) = service.canExecute()
        val isRunning = service.getRunStatus().state == RunState.RUNNING

        // Check if this is the canonical tasq.md
        val canonicalTasqPath = service.getTasqPath()
        val isCanonicalTasq = canonicalTasqPath != null && 
            File(virtualFile.path).canonicalPath == File(canonicalTasqPath).canonicalPath

        // Only show for markdown files that are NOT the canonical tasq.md
        presentation.isVisible = hasQonqrete && isMarkdown && !isCanonicalTasq
        presentation.isEnabled = hasQonqrete && isMarkdown && !isCanonicalTasq && canRun && !isRunning

        presentation.text = if (isRunning) {
            "QonQrete: Running..."
        } else {
            "Run as QonQrete Tasq"
        }
    }
}
