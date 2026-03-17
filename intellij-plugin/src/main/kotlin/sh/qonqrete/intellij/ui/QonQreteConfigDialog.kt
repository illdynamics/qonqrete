/**
 * QonQrete Config Dialog
 * Full run configuration dialog
 *
 * @author WoNQ
 * @version 1.2.0
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.Messages
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.services.*
import java.awt.BorderLayout
import java.awt.Dimension
import javax.swing.*

class QonQreteConfigDialog(
    private val project: Project,
    private val service: QonQreteProjectService
) : DialogWrapper(project) {

    private val settings = QonQreteSettingsState.getInstance()

    private val sensitivitySpinner = JSpinner(SpinnerNumberModel(settings.defaultSensitivity, 0, 16, 1))
    private val cyclesSpinner = JSpinner(SpinnerNumberModel(settings.defaultCycles, 1, 50, 1))
    private val modeCombo = ComboBox(arrayOf("program", "enterprise", "security", "data", "devops", "web"))
    private val autonomousCheckbox = JBCheckBox("Autonomous mode (no human-in-the-loop)")
    private val sqrapyardCheckbox = JBCheckBox("Use Sqrapyard (cache)")
    private val engineCombo = ComboBox(arrayOf("auto", "docker", "podman", "msb"))
    private val tuiCheckbox = JBCheckBox("Enable TUI mode")
    private val wonqreteCheckbox = JBCheckBox("Enable Wonqrete mode")
    private val qonstructionNameField = JBTextField()

    private var validatedConfig: QonQreteRunConfig? = null

    init {
        title = "QonQrete Run Configuration"
        init()

        // Set initial values
        modeCombo.selectedItem = settings.defaultMode
        autonomousCheckbox.isSelected = settings.defaultAutonomous
        sqrapyardCheckbox.isSelected = settings.useSqrapyard
        engineCombo.selectedItem = settings.containerEngine
        tuiCheckbox.isSelected = settings.enableTui
        wonqreteCheckbox.isSelected = settings.enableWonqrete
    }

    override fun createCenterPanel(): JComponent {
        val sensitivityPanel = JPanel(BorderLayout())
        sensitivityPanel.add(sensitivitySpinner, BorderLayout.CENTER)
        sensitivityPanel.add(JBLabel("(0=highest, 16=lowest)"), BorderLayout.EAST)

        val cyclesPanel = JPanel(BorderLayout())
        cyclesPanel.add(cyclesSpinner, BorderLayout.CENTER)
        cyclesPanel.add(JBLabel("(1-50)"), BorderLayout.EAST)

        val builder = FormBuilder.createFormBuilder()
            .addLabeledComponent("Briq Sensitivity:", sensitivityPanel)
            .addLabeledComponent("Cycles:", cyclesPanel)
            .addLabeledComponent("Mode:", modeCombo)
            .addLabeledComponent("Container Engine:", engineCombo)
            .addSeparator()
            .addComponent(autonomousCheckbox)
            .addComponent(sqrapyardCheckbox)
            .addComponent(tuiCheckbox)
            .addComponent(wonqreteCheckbox)
            .addSeparator()
            .addLabeledComponent("Qonstruction Name:", qonstructionNameField)
            .addComponentToRightColumn(JBLabel("(optional, alphanumeric and _/- only)"))

        val panel = JPanel(BorderLayout())
        panel.add(builder.panel, BorderLayout.CENTER)
        panel.border = JBUI.Borders.empty(10)
        panel.preferredSize = Dimension(450, 350)

        return panel
    }

    override fun doOKAction() {
        val qonstructionName = qonstructionNameField.text.trim().takeIf { it.isNotEmpty() }

        // Validate and sanitize qonstruction name
        val finalName = if (qonstructionName != null) {
            val result = service.sanitizeQonstructionName(qonstructionName)
            if (result.wasModified) {
                val confirm = Messages.showYesNoDialog(
                    project,
                    "Qonstruction name will be sanitized:\n\n" +
                    "'${result.original}' → '${result.sanitized}'\n\n" +
                    "Continue with sanitized name?",
                    "Name Sanitization",
                    Messages.getQuestionIcon()
                )
                if (confirm != Messages.YES) {
                    return // Don't close dialog
                }
            }
            result.sanitized
        } else null

        validatedConfig = QonQreteRunConfig(
            sensitivity = sensitivitySpinner.value as Int,
            cycles = cyclesSpinner.value as Int,
            mode = modeCombo.selectedItem as String,
            autonomous = autonomousCheckbox.isSelected,
            qonstructionName = finalName,
            useSqrapyard = sqrapyardCheckbox.isSelected,
            containerEngine = engineCombo.selectedItem as String,
            enableTui = tuiCheckbox.isSelected,
            enableWonqrete = wonqreteCheckbox.isSelected
        )

        super.doOKAction()
    }

    fun getConfig(): QonQreteRunConfig {
        return validatedConfig ?: QonQreteRunConfig.fromSettings()
    }
}
