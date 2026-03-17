/**
 * Run As QonQrete Tasq Action
 * Execute a non-canonical markdown file as a temporary tasq
 *
 * @author WoNQ
 * @version 1.2.0
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

        // Check if QonQrete is available — offer deploy if not
        if (service.getQonQretePath() == null) {
            val choice = Messages.showDialog(
                project,
                "QonQrete runtime not found in this project.",
                "QonQrete Not Found",
                arrayOf("Deploy to Workspace", "Cancel"),
                0,
                Messages.getQuestionIcon()
            )
            if (choice == 0) {
                com.intellij.openapi.actionSystem.ActionManager.getInstance()
                    .getAction("QonQrete.DeployToWorkspace")?.actionPerformed(e)
            }
            return
        }

        val filePath = virtualFile.path

        // Confirm running non-canonical file
        val confirm = Messages.showYesNoDialog(
            project,
            "Run '${virtualFile.name}' as a QonQrete tasq?\n\n" +
            "This will temporarily replace the internal tasq.md and restore it after the run.",
            "Run as QonQrete Tasq",
            Messages.getQuestionIcon()
        )

        if (confirm != Messages.YES) {
            return
        }

        // Auto-init if image is missing
        val initStatus = service.isInitialized()
        if (!initStatus.hasImage && initStatus.hasDockerfile) {
            val initChoice = Messages.showYesNoDialog(
                project,
                "Container image not built yet. Build it now?\n\nThis may take a few minutes.",
                "QonQrete: Init Required",
                Messages.getQuestionIcon()
            )
            if (initChoice != Messages.YES) return
            try {
                service.init()
                service.notify("QonQrete", "Building container image... Run again when init completes.", com.intellij.notification.NotificationType.INFORMATION)
            } catch (ex: Exception) {
                service.notify("QonQrete Error", "Init failed: ${ex.message}", com.intellij.notification.NotificationType.ERROR)
            }
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
