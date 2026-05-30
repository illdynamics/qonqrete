/**
 * Run Tasq Action
 * Execute QonQrete with the default project task file
 *
 * @author WoNQ
 * @version VERSION
 * @license Apache-2.0
 */

package sh.qonqrete.intellij.actions

import java.io.File
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import sh.qonqrete.intellij.util.ActionInvoker
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

        // Check if QonQrete is available - offer deploy if not
        if (service.getQonQretePath() == null) {
            val choice = Messages.showDialog(
                project,
                "QonQrete runtime not found in this project.",
                "QonQrete Not Found",
                arrayOf("Deploy to Workspace", "Configure Path", "Cancel"),
                0,
                Messages.getQuestionIcon()
            )
            when (choice) {
                0 -> ActionInvoker.invokeAction("QonQrete.DeployToWorkspace", e.dataContext, "QonQrete", e.inputEvent)
                1 -> com.intellij.openapi.options.ShowSettingsUtil.getInstance()
                    .showSettingsDialog(project, "QonQrete")
            }
            return
        }

        // Check if a default task file exists - offer create if not
        if (!service.hasTasqFile()) {
            val choice = Messages.showDialog(
                project,
                "No default task file found. Create a starter task file to define your build task.",
                "QonQrete: No Tasq File",
                arrayOf("Create Task File", "Cancel"),
                0,
                Messages.getQuestionIcon()
            )
            if (choice == 0) {
                ActionInvoker.invokeAction("QonQrete.CreateTasq", e.dataContext, "QonQrete", e.inputEvent)
            }
            return
        }

        // Save all documents before running
        FileDocumentManager.getInstance().saveAllDocuments()

        // Auto-init if image is missing
        val initStatus = service.isInitialized()
        if (!initStatus.hasImage && initStatus.hasDockerfile) {
            val choice = Messages.showYesNoDialog(
                project,
                "Container image not built yet. Build it now?\n\nThis may take a few minutes.",
                "QonQrete: Init Required",
                Messages.getQuestionIcon()
            )
            if (choice != Messages.YES) return
            try {
                service.init()
                service.notify("QonQrete", "Building container image... Run Tasq again when init completes.", NotificationType.INFORMATION)
            } catch (ex: Exception) {
                service.notify("QonQrete Error", "Init failed: ${ex.message}", NotificationType.ERROR)
            }
            return
        }

        // Check for missing API keys
        val workingDir = service.getQonQreteWorkingDir()
        if (workingDir != null) {
            val configYaml = "$workingDir/worqspace/config.yaml"
            val missing = SetAIConfigAction.getMissingApiKeys(configYaml)
            if (missing.isNotEmpty()) {
                val providerNames = missing.mapNotNull { key ->
                    when (key) {
                        "OPENAI_API_KEY" -> "OpenAI"
                        "GOOGLE_API_KEY" -> "Gemini"
                        "ANTHROPIC_API_KEY" -> "Anthropic"
                        "OPENROUTER_API_KEY" -> "OpenRouter"
                        "DEEPSEEK_API_KEY" -> "DeepSeek"
                        "QWEN_API_KEY" -> "Qwen"
                        "VENICE_API_KEY" -> "Venice"
                        "MLX_API_KEY" -> "MLX"
                        "LLAMA_CPP_API_KEY" -> "Llama-cpp"
                        else -> key
                    }
                }
                val choice = Messages.showYesNoDialog(
                    project,
                    "API keys needed for: ${providerNames.joinToString(", ")}.\nSet them now?",
                    "QonQrete: Missing API Keys",
                    Messages.getWarningIcon()
                )
                if (choice == Messages.YES) {
                    ActionInvoker.invokeAction("QonQrete.SetAIConfig", e.dataContext, "QonQrete", e.inputEvent)
                    return
                }
            }
        }

        // Save active editor content as the canonical tasq before running,
        // so "Run Tasq" always runs what you're currently editing.
        val editor = com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project)?.selectedTextEditor
        if (editor != null) {
            val psiFile = com.intellij.psi.PsiDocumentManager.getInstance(project)?.getPsiFile(editor.document)
            if (psiFile != null && psiFile.fileType.name.lowercase().contains("markdown")) {
                try {
                    val tasqPath = service.getTasqPath()
                    if (tasqPath != null) {
                        val tasqFile = File(tasqPath)
                        tasqFile.parentFile?.mkdirs()
                        com.intellij.openapi.application.ApplicationManager.getApplication().runWriteAction {
                            com.intellij.openapi.fileEditor.FileDocumentManager.getInstance().saveDocument(editor.document)
                        }
                        // Read the saved content and write to worqspace tasq
                        val editorContent = editor.document.text
                        tasqFile.writeText(editorContent)
                    }
                } catch (_: Exception) {
                    // Fall through — default tasq will be used
                }
            }
        }

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
            !hasTasq -> "QonQrete: No Task File"
            else -> "QonQrete: Run Tasq"
        }
    }

    private fun promptForConfig(project: com.intellij.openapi.project.Project, service: QonQreteProjectService): QonQreteRunConfig? {
        // Determine whether to use a quick-run configuration. Currently always true,
        // but could be toggled based on modifier keys in the future.
        val useQuickRun = true

        return if (useQuickRun) {
            // Start with defaults from settings
            var config = QonQreteRunConfig.fromSettings()

            // Only prompt for a qonstruction name when noSync is enabled
            // (outputs go to qonstructions/<name> instead of repo root).
            // If the user cancels the dialog, abort the run.
            if (config.noSync && config.qonstructionName == null) {
                val nameDialog = QonQreteQonstructionNameDialog(project, service)
                if (!nameDialog.showAndGet()) {
                    return null
                }
                val name = nameDialog.getQonstructionName()
                if (name != null) {
                    config = config.copy(qonstructionName = name)
                }
            }
            config
        } else {
            // When not using quick-run, show the full configuration dialog
            val dialog = QonQreteConfigDialog(project, service)
            if (dialog.showAndGet()) {
                dialog.getConfig()
            } else {
                null
            }
        }
    }
}
