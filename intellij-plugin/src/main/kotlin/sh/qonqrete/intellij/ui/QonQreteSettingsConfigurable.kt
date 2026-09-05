package sh.qonqrete.intellij.ui

import com.intellij.openapi.options.Configurable
import com.intellij.openapi.project.Project
import com.intellij.openapi.fileChooser.FileChooserDescriptor
import com.intellij.openapi.ui.TextBrowseFolderListener
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.util.ui.FormBuilder
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.services.QonQreteSettingsState
import java.awt.BorderLayout
import javax.swing.JComponent
import javax.swing.JPanel

class QonQreteSettingsConfigurable(private val project: Project) : Configurable {
    private val settings = QonQreteSettingsState.getInstance()

    private val qqPathField = TextFieldWithBrowseButton()
    private val configPathField = TextFieldWithBrowseButton()
    private val providersPathField = TextFieldWithBrowseButton()
    private val destinationDirField = TextFieldWithBrowseButton()
    private val noTuiCheckbox = JBCheckBox("Run headless by default (--no-tui)")

    override fun getDisplayName(): String = "QonQrete"

    override fun createComponent(): JComponent {
        qqPathField.addBrowseFolderListener(TextBrowseFolderListener(FileChooserDescriptor(true, false, false, false, false, false), project))
        configPathField.addBrowseFolderListener(TextBrowseFolderListener(FileChooserDescriptor(true, false, false, false, false, false), project))
        providersPathField.addBrowseFolderListener(TextBrowseFolderListener(FileChooserDescriptor(true, false, false, false, false, false), project))
        destinationDirField.addBrowseFolderListener(TextBrowseFolderListener(FileChooserDescriptor(false, true, false, false, false, false), project))

        val builder = FormBuilder.createFormBuilder()
            .addComponent(JBLabel("<html><b>QonQrete v2</b></html>"))
            .addLabeledComponent("qq executable:", qqPathField)
            .addLabeledComponent("config/qq.yaml:", configPathField)
            .addLabeledComponent("config/providers.yaml:", providersPathField)
            .addLabeledComponent("Destination directory:", destinationDirField)
            .addComponent(noTuiCheckbox)

        val panel = JPanel(BorderLayout())
        panel.add(builder.panel, BorderLayout.NORTH)
        panel.border = JBUI.Borders.empty(10)
        return panel
    }

    override fun isModified(): Boolean =
        qqPathField.text != settings.qqPath ||
        configPathField.text != settings.configPath ||
        providersPathField.text != settings.providersPath ||
        destinationDirField.text != settings.destinationDir ||
        noTuiCheckbox.isSelected != settings.noTui

    override fun apply() {
        settings.qqPath = qqPathField.text.trim()
        settings.configPath = configPathField.text.trim()
        settings.providersPath = providersPathField.text.trim()
        settings.destinationDir = destinationDirField.text.trim()
        settings.noTui = noTuiCheckbox.isSelected
    }

    override fun reset() {
        qqPathField.text = settings.qqPath
        configPathField.text = settings.configPath
        providersPathField.text = settings.providersPath
        destinationDirField.text = settings.destinationDir
        noTuiCheckbox.isSelected = settings.noTui
    }
}
