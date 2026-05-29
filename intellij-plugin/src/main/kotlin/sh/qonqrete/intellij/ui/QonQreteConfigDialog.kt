/**
 * QonQrete Config Dialog
 * Full run configuration dialog
 *
 * @author WoNQ
 * @version VERSION
 * @license Apache-2.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import javax.swing.DefaultComboBoxModel
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
    private val autoSensitivityCheckbox = JBCheckBox("Auto briq sensitivity (-B)")
    private val sensitivityLabel = JBLabel("Briq Sensitivity:")

    private val cyclesSpinner = JSpinner(SpinnerNumberModel(settings.defaultCycles, 1, 50, 1))
    private val autoCycleCheckbox = JBCheckBox("Auto cycle determination")
    private val cyclesLabel = JBLabel("Cycles:")

    private val modeCombo = ComboBox(DefaultComboBoxModel(arrayOf("program", "enterprise", "security", "data", "devops", "web")))
    private val autonomousCheckbox = JBCheckBox("Autonomous mode (no human-in-the-loop)")
    private val noSyncCheckbox = JBCheckBox("No repo-root sync (--no-sync)")
    private val sqrapyardCheckbox = JBCheckBox("Seed repository (--seed-repo)")
    private val engineCombo = ComboBox(DefaultComboBoxModel(arrayOf("auto", "docker", "podman")))
    private val qonstructionNameField = JBTextField()

    private var validatedConfig: QonQreteRunConfig? = null

    init {
        title = "QonQrete Run Configuration"
        init()

        // Set initial values
        modeCombo.selectedItem = settings.defaultMode
        autoSensitivityCheckbox.isSelected = settings.defaultAutoBriqSensitivity
        autoCycleCheckbox.isSelected = settings.defaultAutoCycle
        autonomousCheckbox.isSelected = settings.defaultAutonomous
        noSyncCheckbox.isSelected = settings.noSync
        sqrapyardCheckbox.isSelected = settings.useSqrapyard
        engineCombo.selectedItem = settings.containerEngine

        // Hide/show manual controls based on auto toggles
        toggleSensitivityVisibility()
        toggleCyclesVisibility()

        autoSensitivityCheckbox.addChangeListener { toggleSensitivityVisibility() }
        autoCycleCheckbox.addChangeListener { toggleCyclesVisibility() }
    }

    private fun toggleSensitivityVisibility() {
        val auto = autoSensitivityCheckbox.isSelected
        sensitivitySpinner.isVisible = !auto
        sensitivityLabel.isVisible = !auto
    }

    private fun toggleCyclesVisibility() {
        val auto = autoCycleCheckbox.isSelected
        cyclesSpinner.isVisible = !auto
        cyclesLabel.isVisible = !auto
    }

    override fun createCenterPanel(): JComponent {
        val sensitivityPanel = JPanel(BorderLayout())
        sensitivityPanel.add(sensitivitySpinner, BorderLayout.CENTER)
        sensitivityPanel.add(JBLabel("(0=monolithic, 16=max granularity)"), BorderLayout.EAST)

        val cyclesPanel = JPanel(BorderLayout())
        cyclesPanel.add(cyclesSpinner, BorderLayout.CENTER)
        cyclesPanel.add(JBLabel("(1-50)"), BorderLayout.EAST)

        val builder = FormBuilder.createFormBuilder()
            .addLabeledComponent(sensitivityLabel, sensitivityPanel)
            .addComponent(autoSensitivityCheckbox)
            .addLabeledComponent(cyclesLabel, cyclesPanel)
            .addComponent(autoCycleCheckbox)
            .addLabeledComponent("Mode:", modeCombo)
            .addLabeledComponent("Container Engine:", engineCombo)
            .addSeparator()
            .addComponent(autonomousCheckbox)
            .addComponent(sqrapyardCheckbox)
            .addSeparator()
            .addLabeledComponent("Qonstruction Name:", qonstructionNameField)
            .addComponentToRightColumn(JBLabel("(optional, alphanumeric and _/- only)"))
            .addSeparator()
            .addComponent(JBLabel("Advanced:"))
            .addComponent(noSyncCheckbox)

        val panel = JPanel(BorderLayout())
        panel.add(builder.panel, BorderLayout.CENTER)
        panel.border = JBUI.Borders.empty(10)
        panel.preferredSize = Dimension(450, 380)

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
            autoSensitivity = autoSensitivityCheckbox.isSelected,
            autoCycle = autoCycleCheckbox.isSelected,
            cycles = cyclesSpinner.value as Int,
            mode = modeCombo.selectedItem as String,
            autonomous = autonomousCheckbox.isSelected,
            noSync = noSyncCheckbox.isSelected,
            qonstructionName = finalName,
            useSqrapyard = sqrapyardCheckbox.isSelected,
            containerEngine = engineCombo.selectedItem as String
        )

        super.doOKAction()
    }

    fun getConfig(): QonQreteRunConfig {
        return validatedConfig ?: QonQreteRunConfig.fromSettings()
    }
}
