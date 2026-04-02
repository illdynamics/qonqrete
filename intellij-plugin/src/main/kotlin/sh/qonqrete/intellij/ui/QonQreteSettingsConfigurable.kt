/**
 * QonQrete Settings Configurable
 * Settings panel in Tools → QonQrete
 *
 * @author WoNQ
 * @version 1.2.2
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.openapi.fileChooser.FileChooserDescriptorFactory
import com.intellij.openapi.options.Configurable
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.TextFieldWithBrowseButton
import com.intellij.ui.components.JBCheckBox
import com.intellij.ui.components.JBLabel
import com.intellij.util.ui.FormBuilder
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.services.QonQreteSettingsState
import java.awt.BorderLayout
import javax.swing.JComponent
import javax.swing.JPanel
import javax.swing.JSpinner
import javax.swing.SpinnerNumberModel

class QonQreteSettingsConfigurable(private val project: Project) : Configurable {

    private val settings = QonQreteSettingsState.getInstance()

    private val sensitivitySpinner = JSpinner(SpinnerNumberModel(settings.defaultSensitivity, 0, 16, 1))
    private val cyclesSpinner = JSpinner(SpinnerNumberModel(settings.defaultCycles, 0, 50, 1))
    private val modeCombo = ComboBox(arrayOf("program", "innovative", "enterprise", "security", "data", "devops", "web"))
    private val autonomousCheckbox = JBCheckBox("Autonomous mode by default")
    private val sqrapyardCheckbox = JBCheckBox("Use Sqrapyard by default")
    private val engineCombo = ComboBox(arrayOf("auto", "docker", "podman", "msb"))
    private val tuiCheckbox = JBCheckBox("Enable TUI mode by default")
    private val wonqreteCheckbox = JBCheckBox("Enable Wonqrete mode by default")
    private val autoOpenToolWindowCheckbox = JBCheckBox("Auto-open tool window on run")
    private val qageListLimitSpinner = JSpinner(SpinnerNumberModel(settings.qageListLimit, 1, 100, 1))
    private val markerTimeoutSpinner = JSpinner(SpinnerNumberModel(settings.markerTimeoutMinutes, 1, 240, 1))
    
    private val customQonqretePathField = TextFieldWithBrowseButton()
    private val customBashPathField = TextFieldWithBrowseButton()

    override fun getDisplayName(): String = "QonQrete"

    override fun createComponent(): JComponent {
        // Set up file choosers
        customQonqretePathField.addBrowseFolderListener(
            "Select qonqrete.sh",
            "Select the QonQrete script",
            project,
            FileChooserDescriptorFactory.createSingleFileDescriptor()
        )

        customBashPathField.addBrowseFolderListener(
            "Select Bash",
            "Select the bash executable",
            project,
            FileChooserDescriptorFactory.createSingleFileDescriptor()
        )

        val builder = FormBuilder.createFormBuilder()
            .addComponent(JBLabel("<html><b>Default Run Configuration</b></html>"))
            .addLabeledComponent("Briq Sensitivity:", sensitivitySpinner)
            .addLabeledComponent("Cycles:", cyclesSpinner)
            .addLabeledComponent("Mode:", modeCombo)
            .addLabeledComponent("Container Engine:", engineCombo)
            .addComponent(autonomousCheckbox)
            .addComponent(sqrapyardCheckbox)
            .addComponent(tuiCheckbox)
            .addComponent(wonqreteCheckbox)
            .addSeparator()
            .addComponent(JBLabel("<html><b>Plugin Behavior</b></html>"))
            .addComponent(autoOpenToolWindowCheckbox)
            .addLabeledComponent("Max qages to show:", qageListLimitSpinner)
            .addLabeledComponent("Marker timeout (minutes):", markerTimeoutSpinner)
            .addSeparator()
            .addComponent(JBLabel("<html><b>Custom Paths</b></html>"))
            .addLabeledComponent("QonQrete script:", customQonqretePathField)
            .addLabeledComponent("Bash executable:", customBashPathField)

        val panel = JPanel(BorderLayout())
        panel.add(builder.panel, BorderLayout.NORTH)
        panel.border = JBUI.Borders.empty(10)

        return panel
    }

    override fun isModified(): Boolean {
        return sensitivitySpinner.value != settings.defaultSensitivity ||
            cyclesSpinner.value != settings.defaultCycles ||
            modeCombo.selectedItem != settings.defaultMode ||
            autonomousCheckbox.isSelected != settings.defaultAutonomous ||
            sqrapyardCheckbox.isSelected != settings.useSqrapyard ||
            engineCombo.selectedItem != settings.containerEngine ||
            tuiCheckbox.isSelected != settings.enableTui ||
            wonqreteCheckbox.isSelected != settings.enableWonqrete ||
            autoOpenToolWindowCheckbox.isSelected != settings.autoOpenToolWindowOnRun ||
            qageListLimitSpinner.value != settings.qageListLimit ||
            markerTimeoutSpinner.value != settings.markerTimeoutMinutes ||
            customQonqretePathField.text != settings.customQonqretePath ||
            customBashPathField.text != settings.customBashPath
    }

    override fun apply() {
        settings.defaultSensitivity = sensitivitySpinner.value as Int
        settings.defaultCycles = cyclesSpinner.value as Int
        settings.defaultMode = modeCombo.selectedItem as String
        settings.defaultAutonomous = autonomousCheckbox.isSelected
        settings.useSqrapyard = sqrapyardCheckbox.isSelected
        settings.containerEngine = engineCombo.selectedItem as String
        settings.enableTui = tuiCheckbox.isSelected
        settings.enableWonqrete = wonqreteCheckbox.isSelected
        settings.autoOpenToolWindowOnRun = autoOpenToolWindowCheckbox.isSelected
        settings.qageListLimit = qageListLimitSpinner.value as Int
        settings.markerTimeoutMinutes = markerTimeoutSpinner.value as Int
        settings.customQonqretePath = customQonqretePathField.text
        settings.customBashPath = customBashPathField.text
    }

    override fun reset() {
        sensitivitySpinner.value = settings.defaultSensitivity
        cyclesSpinner.value = settings.defaultCycles
        modeCombo.selectedItem = settings.defaultMode
        autonomousCheckbox.isSelected = settings.defaultAutonomous
        sqrapyardCheckbox.isSelected = settings.useSqrapyard
        engineCombo.selectedItem = settings.containerEngine
        tuiCheckbox.isSelected = settings.enableTui
        wonqreteCheckbox.isSelected = settings.enableWonqrete
        autoOpenToolWindowCheckbox.isSelected = settings.autoOpenToolWindowOnRun
        qageListLimitSpinner.value = settings.qageListLimit
        markerTimeoutSpinner.value = settings.markerTimeoutMinutes
        customQonqretePathField.text = settings.customQonqretePath
        customBashPathField.text = settings.customBashPath
    }
}
