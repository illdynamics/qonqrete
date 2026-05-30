/**
 * QonQrete Tool Window Panel
 * Compact control panel with run configuration and actions.
 *
 * @author WoNQ
 * @version VERSION
 * @license Apache-2.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import javax.swing.DefaultComboBoxModel
import com.intellij.openapi.ui.Messages
import com.intellij.ui.JBColor
import com.intellij.ui.components.*
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.util.ActionInvoker
import sh.qonqrete.intellij.services.*
import java.awt.*
import javax.swing.*
import javax.swing.border.TitledBorder

class QonQreteToolWindowPanel(private val project: Project) : JPanel(BorderLayout()), Disposable {

    private val service = QonQreteProjectService.getInstance(project)
    private val settings = QonQreteSettingsState.getInstance()

    // Status labels
    private val shellStatusLabel = JBLabel("Checking...")
    private val runStatusLabel = JBLabel("Idle")
    private val initStatusLabel = JBLabel("Checking...")
    private val versionLabel = JBLabel("-")

    // Config controls
    private val sensitivitySpinner = JSpinner(SpinnerNumberModel(settings.defaultSensitivity, 0, 16, 1)).apply {
        toolTipText = "Briq sensitivity (0-16). Higher = more briqs."
    }
    private val autoSensitivityCheckbox = JBCheckBox("Auto briq sens", settings.defaultAutoBriqSensitivity).apply {
        toolTipText = "Automatic briq sensitivity detection"
    }
    private val cyclesSpinner = JSpinner(SpinnerNumberModel(settings.defaultCycles, 1, 50, 1)).apply {
        toolTipText = "AI iteration cycles (1-50)"
    }
    private val autoCycleCheckbox = JBCheckBox("Auto cycles", settings.defaultAutoCycle).apply {
        toolTipText = "Automatic cycle amount determination"
    }
    private val modeCombo = ComboBox(DefaultComboBoxModel(arrayOf("program", "enterprise", "security", "data", "devops", "web"))).apply {
        toolTipText = "QonQrete execution mode"
    }
    private val autonomousCheckbox = JBCheckBox("Autonomous", settings.defaultAutonomous).apply {
        toolTipText = "Autonomous mode (--auto)"
    }
    private val noSyncCheckbox = JBCheckBox("No Sync", settings.noSync).apply {
        toolTipText = "Skip repo-root sync-back (--no-sync)"
    }
    private val sqrapyardCheckbox = JBCheckBox("Seed Repo", true).apply {
        toolTipText = "Seed from repo before run (--seed-repo)"
        isSelected = true
    }
    private val engineCombo = ComboBox(DefaultComboBoxModel(arrayOf("auto", "docker", "podman"))).apply {
        toolTipText = "Container engine"
    }
    private val qonstructionNameLabel = JBLabel("Qonstruction:")
    private val qonstructionNameField = JBTextField().apply {
        toolTipText = "Optional build name (only used with No Sync)"
    }

    // Action buttons
    private val runButton = JButton("▶ Run Tasq")
    private val deployButton = JButton("⬡ Deploy")
    private val createTasqButton = JButton("+ Create Tasq")
    private val aiConfigButton = JButton("🤖 AI Config")
    private val initButton = JButton("⚙ Init")
    private val resumeButton = JButton("↻ Resume")
    private val openTasqButton = JButton("📝 Open Tasq")

    private var refreshCallback: (() -> Unit)? = null

    init {
        border = JBUI.Borders.empty(8)
        buildUI()
        setupListeners()
        refreshState()
        // Apply initial visibility
        toggleSensitivityVisibility()
        toggleCyclesVisibility()
        toggleQonstructionVisibility()
    }

    private fun toggleSensitivityVisibility() {
        val auto = autoSensitivityCheckbox.isSelected
        sensitivitySpinner.isVisible = !auto
    }

    private fun toggleCyclesVisibility() {
        val auto = autoCycleCheckbox.isSelected
        cyclesSpinner.isVisible = !auto
    }

    private fun toggleQonstructionVisibility() {
        val show = noSyncCheckbox.isSelected
        qonstructionNameLabel.isVisible = show
        qonstructionNameField.isVisible = show
    }

    private fun buildUI() {
        val mainPanel = JPanel()
        mainPanel.layout = BoxLayout(mainPanel, BoxLayout.Y_AXIS)

        // === STATUS PANEL ===
        val statusPanel = JPanel(GridBagLayout())
        statusPanel.border = TitledBorder("Status")
        val gbc = GridBagConstraints().apply { anchor = GridBagConstraints.WEST; insets = JBUI.insets(2) }

        gbc.gridx = 0; gbc.gridy = 0
        statusPanel.add(JBLabel("Shell:"), gbc)
        gbc.gridx = 1
        statusPanel.add(shellStatusLabel, gbc)

        gbc.gridx = 0; gbc.gridy = 1
        statusPanel.add(JBLabel("Run:"), gbc)
        gbc.gridx = 1
        statusPanel.add(runStatusLabel, gbc)

        gbc.gridx = 0; gbc.gridy = 2
        statusPanel.add(JBLabel("Container:"), gbc)
        gbc.gridx = 1
        statusPanel.add(initStatusLabel, gbc)

        gbc.gridx = 0; gbc.gridy = 3
        statusPanel.add(JBLabel("Version:"), gbc)
        gbc.gridx = 1
        statusPanel.add(versionLabel, gbc)

        statusPanel.maximumSize = Dimension(Int.MAX_VALUE, statusPanel.preferredSize.height)
        mainPanel.add(statusPanel)
        mainPanel.add(Box.createVerticalStrut(6))

        // === CONFIG PANEL ===
        val configPanel = JPanel(GridBagLayout())
        configPanel.border = TitledBorder("Configuration")
        val cgbc = GridBagConstraints().apply {
            anchor = GridBagConstraints.WEST; insets = JBUI.insets(2); fill = GridBagConstraints.HORIZONTAL
        }

        var row = 0
        cgbc.gridx = 0; cgbc.gridy = row; cgbc.weightx = 0.0
        configPanel.add(JBLabel("Sensitivity:"), cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        configPanel.add(sensitivitySpinner, cgbc)
        cgbc.gridwidth = 1

        row++
        cgbc.gridx = 0; cgbc.gridy = row; cgbc.gridwidth = 2; cgbc.weightx = 1.0
        configPanel.add(autoSensitivityCheckbox, cgbc)

        row++
        cgbc.gridx = 0; cgbc.gridy = row; cgbc.weightx = 0.0; cgbc.gridwidth = 1
        configPanel.add(JBLabel("Cycles:"), cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        configPanel.add(cyclesSpinner, cgbc)

        row++
        cgbc.gridx = 0; cgbc.gridy = row; cgbc.gridwidth = 2; cgbc.weightx = 1.0
        configPanel.add(autoCycleCheckbox, cgbc)

        row++
        cgbc.gridx = 0; cgbc.gridy = row; cgbc.weightx = 0.0; cgbc.gridwidth = 1
        configPanel.add(JBLabel("Mode:"), cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        modeCombo.selectedItem = settings.defaultMode
        configPanel.add(modeCombo, cgbc)

        row++
        cgbc.gridx = 0; cgbc.gridy = row; cgbc.weightx = 0.0
        configPanel.add(JBLabel("Engine:"), cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        engineCombo.selectedItem = settings.containerEngine
        configPanel.add(engineCombo, cgbc)

        row++
        cgbc.gridx = 0; cgbc.gridy = row; cgbc.gridwidth = 2
        val checkboxPanel = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        checkboxPanel.add(autonomousCheckbox)
        checkboxPanel.add(noSyncCheckbox)
        checkboxPanel.add(sqrapyardCheckbox)
        configPanel.add(checkboxPanel, cgbc)

        row++
        cgbc.gridx = 0; cgbc.gridy = row; cgbc.gridwidth = 1; cgbc.weightx = 0.0
        configPanel.add(qonstructionNameLabel, cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        configPanel.add(qonstructionNameField, cgbc)

        configPanel.maximumSize = Dimension(Int.MAX_VALUE, configPanel.preferredSize.height)
        mainPanel.add(configPanel)
        mainPanel.add(Box.createVerticalStrut(6))

        // === ACTION BUTTONS (vertical stack) ===
        val buttonPanel = JPanel()
        buttonPanel.layout = BoxLayout(buttonPanel, BoxLayout.Y_AXIS)
        
        val row1 = JPanel(FlowLayout(FlowLayout.LEFT))
        row1.add(runButton)
        row1.add(deployButton)
        row1.add(createTasqButton)
        row1.add(aiConfigButton)
        
        val row2 = JPanel(FlowLayout(FlowLayout.LEFT))
        row2.add(initButton)
        row2.add(resumeButton)
        row2.add(openTasqButton)
        
        buttonPanel.add(row1)
        buttonPanel.add(row2)
        buttonPanel.maximumSize = Dimension(Int.MAX_VALUE, buttonPanel.preferredSize.height)
        mainPanel.add(buttonPanel)

        val scrollPane = JBScrollPane(mainPanel)
        scrollPane.border = null
        // Half-width: ~250px
        scrollPane.preferredSize = Dimension(250, 500)
        add(scrollPane, BorderLayout.CENTER)
    }

    private fun setupListeners() {
        runButton.addActionListener { executeRun() }
        deployButton.addActionListener { executeDeploy() }
        createTasqButton.addActionListener { executeCreateTasq() }
        aiConfigButton.addActionListener { executeAIConfig() }
        initButton.addActionListener { executeInit() }
        resumeButton.addActionListener { executeResumeInteractive() }
        openTasqButton.addActionListener { openTasqFile() }

        autoSensitivityCheckbox.addChangeListener { toggleSensitivityVisibility() }
        autoCycleCheckbox.addChangeListener { toggleCyclesVisibility() }
        noSyncCheckbox.addChangeListener { toggleQonstructionVisibility() }

        service.onRunStateChange { status ->
            ApplicationManager.getApplication().invokeLater { updateRunStatus(status) }
        }
        service.onShellStateChange { info ->
            ApplicationManager.getApplication().invokeLater { updateShellStatus(info) }
        }
        refreshCallback = { refreshState() }
        service.onRefresh(refreshCallback!!)
    }

    private fun refreshState() {
        updateShellStatus(service.getShellInfo())
        updateRunStatus(service.getRunStatus())

        val initStatus = service.isInitialized()
        initStatusLabel.text = when {
            !initStatus.hasDockerfile -> "❌ No Dockerfile"
            !initStatus.hasImage -> "⚠️ Not built"
            else -> "✅ Ready (${initStatus.engine})"
        }

        versionLabel.text = service.getVersion() ?: "-"
        updateButtonStates()
    }

    private fun updateShellStatus(info: ShellInfo) {
        shellStatusLabel.text = when (info.state) {
            ShellState.NO_BASH -> "❌ No Bash"
            ShellState.VERIFYING -> "⏳ Verifying..."
            ShellState.READY -> "✅ ${info.shellType}"
            ShellState.SHELL_ERROR -> "⚠️ Error"
        }
        shellStatusLabel.foreground = when (info.state) {
            ShellState.NO_BASH, ShellState.SHELL_ERROR -> JBColor.RED
            ShellState.VERIFYING -> JBColor.ORANGE
            ShellState.READY -> JBColor.GREEN.darker()
        }
        updateButtonStates()
    }

    private fun updateRunStatus(status: RunStatus) {
        runStatusLabel.text = when (status.state) {
            RunState.IDLE -> "Idle"
            RunState.RUNNING -> "🔄 Running..."
            RunState.COMPLETED -> "✅ Done (${status.exitCode})"
            RunState.FAILED -> "❌ Failed (${status.exitCode})"
            RunState.TIMEOUT -> "⏱️ Timeout"
        }
        runStatusLabel.foreground = when (status.state) {
            RunState.IDLE -> JBColor.foreground()
            RunState.RUNNING -> JBColor.BLUE
            RunState.COMPLETED -> JBColor.GREEN.darker()
            RunState.FAILED -> JBColor.RED
            RunState.TIMEOUT -> JBColor.ORANGE
        }
        updateButtonStates()
    }

    private fun updateButtonStates() {
        val (canRun, _, _) = service.canExecute()
        val hasQonqrete = service.getQonQretePath() != null
        val hasTasq = service.hasTasqFile()
        val isRunning = service.getRunStatus().state == RunState.RUNNING

        runButton.isEnabled = canRun && hasQonqrete && hasTasq && !isRunning
        initButton.isEnabled = canRun && hasQonqrete && !isRunning
        resumeButton.isEnabled = canRun && hasQonqrete && !isRunning
        openTasqButton.isEnabled = hasQonqrete && hasTasq
        deployButton.isEnabled = !isRunning
        createTasqButton.isEnabled = !isRunning
        aiConfigButton.isEnabled = hasQonqrete && !isRunning
        runButton.text = if (isRunning) "⏳ Running..." else "▶ Run Tasq"
    }

    private fun openTasqFile() {
        val tasqPath = service.getTasqPath()
        if (tasqPath != null && java.io.File(tasqPath).exists()) {
            val vf = com.intellij.openapi.vfs.LocalFileSystem.getInstance().refreshAndFindFileByPath(tasqPath)
            if (vf != null) {
                com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project).openFile(vf, true)
            }
        } else {
            service.notify("QonQrete", "No default task file found", NotificationType.WARNING)
        }
    }

    private fun getConfigFromUI(): QonQreteRunConfig? {
        val rawName = qonstructionNameField.text.trim()
        var finalName: String? = null

        if (rawName.isNotEmpty()) {
            val result = service.sanitizeQonstructionName(rawName)
            if (result.wasModified) {
                val confirm = Messages.showYesNoDialog(
                    project,
                    "Qonstruction name will be sanitized:\n\n'${result.original}' → '${result.sanitized}'\n\nProceed?",
                    "Sanitization Required", Messages.getQuestionIcon()
                )
                if (confirm != Messages.YES) return null
            }
            finalName = result.sanitized
        }

        return QonQreteRunConfig(
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
    }

    private fun executeRun() {
        val (canRun, reason, _) = service.canExecute()
        if (!canRun) { service.notify("QonQrete", reason ?: "Cannot run", NotificationType.WARNING); return }
        if (!service.hasTasqFile()) { service.notify("QonQrete", "No default task file found.", NotificationType.WARNING); return }
        FileDocumentManager.getInstance().saveAllDocuments()

        val initStatus = service.isInitialized()
        if (!initStatus.hasImage && initStatus.hasDockerfile) {
            val choice = Messages.showYesNoDialog(project, "Container image not built yet. Build it now?", "QonQrete: Init Required", Messages.getQuestionIcon())
            if (choice != Messages.YES) return
            try {
                service.init()
                service.notify("QonQrete", "Building... Run Tasq again when complete.", NotificationType.INFORMATION)
            } catch (e: Exception) { service.notify("QonQrete Error", "Init failed: ${e.message}", NotificationType.ERROR) }
            return
        }

        val config = getConfigFromUI() ?: return
        try { service.run(config) }
        catch (e: Exception) { service.notify("QonQrete Error", e.message ?: "Unknown error", NotificationType.ERROR) }
    }

    private fun executeInit() {
        val (canRun, reason, _) = service.canExecute()
        if (!canRun) { service.notify("QonQrete", reason ?: "Cannot init", NotificationType.WARNING); return }
        try { service.init() }
        catch (e: Exception) { service.notify("QonQrete Error", e.message ?: "Unknown error", NotificationType.ERROR) }
    }

    private fun executeDeploy() {
        ActionInvoker.invokeAction("QonQrete.DeployToWorkspace", com.intellij.openapi.actionSystem.DataContext { dataId ->
            when {
                com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.`is`(dataId) -> project
                else -> null
            }
        })
    }

    private fun executeCreateTasq() {
        ActionInvoker.invokeAction("QonQrete.CreateTasq", com.intellij.openapi.actionSystem.DataContext { dataId ->
            when {
                com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.`is`(dataId) -> project
                else -> null
            }
        })
    }

    private fun executeAIConfig() {
        ActionInvoker.invokeAction("QonQrete.SetAIConfig", com.intellij.openapi.actionSystem.DataContext { dataId ->
            when {
                com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.`is`(dataId) -> project
                else -> null
            }
        })
    }

    private fun executeResumeInteractive() {
        service.notify("QonQrete", "Use the Run Config dialog to resume from a qage.", NotificationType.INFORMATION)
    }

    override fun dispose() {
        refreshCallback?.let { service.removeRefreshListener(it) }
    }
}
