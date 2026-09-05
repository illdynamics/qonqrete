/**
 * QonQrete v2 actions.
 */
package sh.qonqrete.intellij.actions

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import sh.qonqrete.intellij.services.QonQreteProjectService
import sh.qonqrete.intellij.services.QonQreteRunConfig
import sh.qonqrete.intellij.services.QonQreteSettingsState
import sh.qonqrete.intellij.util.QonQreteConfig
import java.io.File

private fun projectOf(e: AnActionEvent): Project? = e.project ?: e.dataContext.getData(CommonDataKeys.PROJECT)

private fun defaultDestination(project: Project): String {
    val settings = QonQreteSettingsState.getInstance()
    if (settings.destinationDir.isNotBlank()) return settings.destinationDir
    return project.basePath ?: System.getProperty("user.home")
}

class RunCurrentFileAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        val service = QonQreteProjectService.getInstance(project)
        if (!service.isAvailable()) {
            service.notify("QonQrete", "qq CLI not found. Set qqPath in Settings → Tools → QonQrete.", NotificationType.WARNING)
            return
        }
        val editor = FileEditorManager.getInstance(project).selectedTextEditor ?: run {
            service.notify("QonQrete", "Open a file to run as the QonQrete task.", NotificationType.WARNING)
            return
        }
        FileDocumentManager.getInstance().saveDocument(editor.document)
        val file = FileDocumentManager.getInstance().getFile(editor.document)?.path
        if (file == null) {
            service.notify("QonQrete", "The current editor has no file on disk.", NotificationType.WARNING)
            return
        }
        val dest = defaultDestination(project)
        service.runTask(QonQreteRunConfig(taskFile = file, destinationDir = dest, noTui = QonQreteSettingsState.getInstance().noTui))
    }
}

class RunTaskFileAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        val service = QonQreteProjectService.getInstance(project)
        val descriptor = com.intellij.openapi.fileChooser.FileChooserDescriptor(true, false, false, false, false, false)
        descriptor.title = "Select a QonQrete task file"
        val chosen = com.intellij.openapi.fileChooser.FileChooser.chooseFile(descriptor, project, null) ?: return
        service.runTask(QonQreteRunConfig(
            taskFile = chosen.path,
            destinationDir = defaultDestination(project),
            noTui = QonQreteSettingsState.getInstance().noTui
        ))
    }
}

class ConfigureAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        val service = QonQreteProjectService.getInstance(project)
        val providers = QonQreteConfig.listProviders(project)
        if (providers.isEmpty()) {
            service.notify("QonQrete", "Could not load providers from providers.yaml.", NotificationType.ERROR)
            return
        }
        val current = QonQreteConfig.readProviderAndModel(project)
        val providerNames = providers.map { it.name }.toTypedArray()
        val provider = Messages.showEditableChooseDialog(
            "Select the QonQrete provider.",
            "QonQrete Provider",
            Messages.getQuestionIcon(),
            providerNames,
            providerNames.firstOrNull { it == current?.first } ?: providerNames.first(),
            null
        ) ?: return

        val models = providers.firstOrNull { it.name == provider }?.models.orEmpty()
        val modelOptions = if (models.isNotEmpty()) models.toTypedArray() else arrayOf("custom")
        val defaultModel = models.firstOrNull() ?: "custom"
        val model = Messages.showEditableChooseDialog(
            "Select the model (applied to all QonQrete roles).",
            "QonQrete Model",
            Messages.getQuestionIcon(),
            modelOptions,
            models.firstOrNull() ?: "custom",
            null
        ) ?: return

        val finalModel = if (model == "custom") {
            Messages.showInputDialog(project, "Enter the custom model id for $provider:", "QonQrete Model", Messages.getQuestionIcon()) ?: return
        } else model

        if (QonQreteConfig.saveProviderAndModel(project, provider, finalModel)) {
            service.notify("QonQrete", "Configured: $provider / $finalModel")
        } else {
            service.notify("QonQrete", "Could not save config. Set configPath in Settings → Tools → QonQrete.", NotificationType.ERROR)
        }
    }
}

class OpenConfigAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        QonQreteProjectService.getInstance(project).openConfig()
    }
}

class DoctorAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        QonQreteProjectService.getInstance(project).runDoctor()
    }
}

class VerifyAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        QonQreteProjectService.getInstance(project).runVerify()
    }
}

class CleanupAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        val service = QonQreteProjectService.getInstance(project)
        val root = defaultDestination(project)
        service.runCleanup(root)
    }
}

class ReplayAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        QonQreteProjectService.getInstance(project).runReplay(null)
    }
}

class RunsAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        QonQreteProjectService.getInstance(project).runRuns()
    }
}

class ExecAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        val command = Messages.showInputDialog(project, "Command to run through qq exec:", "QonQrete Exec", Messages.getQuestionIcon()) ?: return
        if (command.isNotBlank()) QonQreteProjectService.getInstance(project).runExec(command)
    }
}

class ChatAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = projectOf(e) ?: return
        QonQreteProjectService.getInstance(project).runChat()
    }
}
