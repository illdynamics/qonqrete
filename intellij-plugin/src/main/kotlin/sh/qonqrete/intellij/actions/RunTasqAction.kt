/**
 * Run Tasq Action
 * Execute QonQrete with tasq.md (synced from workspace root)
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
                0 -> com.intellij.openapi.actionSystem.ActionManager.getInstance()
                    .getAction("QonQrete.DeployToWorkspace")?.actionPerformed(e)
                1 -> com.intellij.openapi.options.ShowSettingsUtil.getInstance()
                    .showSettingsDialog(project, "QonQrete")
            }
            return
        }

        // Check if tasq.md exists - offer create if not
        if (!service.hasTasqFile()) {
            val choice = Messages.showDialog(
                project,
                "No tasq.md found. Create one to define your build task.",
                "QonQrete: No Tasq File",
                arrayOf("Create tasq.md", "Cancel"),
                0,
                Messages.getQuestionIcon()
            )
            if (choice == 0) {
                com.intellij.openapi.actionSystem.ActionManager.getInstance()
                    .getAction("QonQrete.CreateTasq")?.actionPerformed(e)
            }
            return
        }

        // Save all documents before running
        FileDocumentManager.getInstance().saveAllDocuments()

        // Sync workspace-root tasq.md into internal runtime location
        service.syncRootTasqToInternal()

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
                    com.intellij.openapi.actionSystem.ActionManager.getInstance()
                        .getAction("QonQrete.SetAIConfig")?.actionPerformed(e)
                    return
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
            !hasTasq -> "QonQrete: No tasq.md"
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

            // Always prompt for a qonstruction name if none has been provided. This ensures
            // that the CLI receives a -n argument and the resulting qage directory is renamed
            // appropriately. If the user cancels the dialog, abort the run.
            if (config.qonstructionName == null) {
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
