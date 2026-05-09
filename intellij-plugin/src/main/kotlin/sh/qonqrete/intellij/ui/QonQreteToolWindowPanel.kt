/**
 * QonQrete Tool Window Panel
 * Full control panel with status, config, and COMPLETE artifact browser
 * 
 * v1.3.0 IMPROVEMENTS:
 * - Auto-refresh when run completes via service.onRefresh()
 * - "Open Tasq" button for quick editing
 * - "Clean All" button with confirmation
 * - Tooltips on ALL config controls
 * - Qage timestamps displayed in list
 * - Implements Disposable for proper cleanup
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.ide.BrowserUtil
import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.ui.JBColor
import com.intellij.ui.components.*
import com.intellij.ui.treeStructure.Tree
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.services.*
import sh.qonqrete.intellij.ui.QonQreteQonstructionNameDialog
import java.awt.*
import java.io.File
import javax.swing.*
import javax.swing.border.TitledBorder
import javax.swing.tree.DefaultMutableTreeNode
import javax.swing.tree.DefaultTreeModel

class QonQreteToolWindowPanel(private val project: Project) : JPanel(BorderLayout()), Disposable {

    private val service = QonQreteProjectService.getInstance(project)
    private val settings = QonQreteSettingsState.getInstance()

    // Status labels
    private val shellStatusLabel = JBLabel("Checking...")
    private val runStatusLabel = JBLabel("Idle")
    private val initStatusLabel = JBLabel("Checking...")
    private val versionLabel = JBLabel("-")

    // Config controls with tooltips
    private val sensitivitySpinner = JSpinner(SpinnerNumberModel(settings.defaultSensitivity, 0, 16, 1)).apply {
        toolTipText = "Briq sensitivity (0-16). Higher = more briqs generated."
    }
    private val autoSensitivityCheckbox = JBCheckBox("Auto briq sens", settings.defaultAutoBriqSensitivity).apply {
        toolTipText = "Enable automatic briq sensitivity detection (--auto-briq-sensitivity)"
    }
    private val cyclesSpinner = JSpinner(SpinnerNumberModel(settings.defaultCycles, 1, 50, 1)).apply {
        toolTipText = "Number of AI cycles (1-50). More cycles = more refinement."
    }
    private val modeCombo = ComboBox(arrayOf("program", "enterprise", "security", "data", "devops", "web")).apply {
        toolTipText = "QonQrete mode: program (general), enterprise, security, data, devops, or web"
    }
    private val autonomousCheckbox = JBCheckBox("Autonomous", settings.defaultAutonomous).apply {
        toolTipText = "Enable autonomous mode (--auto). AI makes decisions without prompts."
    }
    private val noSyncCheckbox = JBCheckBox("No Sync", settings.noSync).apply {
        toolTipText = "Skip repo-root sync-back and keep output in qage/qonstructions (--no-sync)"
    }
    private val sqrapyardCheckbox = JBCheckBox("Seed Repo", settings.useSqrapyard).apply {
        toolTipText = "Seed qodeyard from repository before run (--seed-repo)"
    }
    private val engineCombo = ComboBox(arrayOf("auto", "docker", "podman")).apply {
        toolTipText = "Container engine: auto (detect), docker, or podman"
    }
    private val qonstructionNameField = JBTextField().apply {
        toolTipText = "Optional name for this build. Invalid characters will be replaced with underscores."
    }

    // Action buttons
    private val runButton = JButton("▶ Run Tasq")
    private val initButton = JButton("⚙ Init")
    private val resumeButton = JButton("↻ Resume")
    private val cleanButton = JButton("🗑 Clean")
    private val deployButton = JButton("⬡ Deploy").apply {
        toolTipText = "Deploy QonQrete runtime to this project (.qonqrete/)"
    }
    private val createTasqButton = JButton("+ Create Tasq").apply {
        toolTipText = "Create a starter tasq.md at project root"
    }
    private val aiConfigButton = JButton("🤖 AI Config").apply {
        toolTipText = "Set AI providers, models, and API keys"
    }
    private val cleanAllButton = JButton("🗑 Clean All").apply {
        toolTipText = "Delete ALL qages (with confirmation)"
    }
    private val openTasqButton = JButton("📝 Open Tasq").apply {
        toolTipText = "Open tasq.md in editor"
    }
    private val refreshButton = JButton("↺ Refresh")

    // Qage browser with timestamps
    private data class QageListItem(val name: String, val timestamp: String, val artifactCount: Int) {
        override fun toString() = "$name ($timestamp) [$artifactCount]"
    }
    private val qageListModel = DefaultListModel<QageListItem>()
    private val qageList = JBList(qageListModel)
    private val artifactTree = Tree()
    private val artifactTreeRoot = DefaultMutableTreeNode("Artifacts")
    private val artifactTreeModel = DefaultTreeModel(artifactTreeRoot)
    
    // Refresh callback reference for disposal
    private var refreshCallback: (() -> Unit)? = null

    init {
        border = JBUI.Borders.empty(8)
        artifactTree.model = artifactTreeModel
        buildUI()
        setupListeners()
        refreshState()
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
        mainPanel.add(Box.createVerticalStrut(8))

        // === CONFIG PANEL ===
        val configPanel = JPanel(GridBagLayout())
        configPanel.border = TitledBorder("Configuration")
        val cgbc = GridBagConstraints().apply { 
            anchor = GridBagConstraints.WEST; insets = JBUI.insets(2); fill = GridBagConstraints.HORIZONTAL 
        }

        cgbc.gridx = 0; cgbc.gridy = 0; cgbc.weightx = 0.0
        configPanel.add(JBLabel("Sensitivity:").apply { toolTipText = "Briq sensitivity (0-16)" }, cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        configPanel.add(sensitivitySpinner, cgbc)

        cgbc.gridx = 0; cgbc.gridy = 1; cgbc.weightx = 0.0
        configPanel.add(JBLabel("Cycles:").apply { toolTipText = "AI iteration cycles (1-50)" }, cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        configPanel.add(cyclesSpinner, cgbc)

        cgbc.gridx = 0; cgbc.gridy = 2; cgbc.weightx = 0.0
        configPanel.add(JBLabel("Mode:").apply { toolTipText = "QonQrete execution mode" }, cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        modeCombo.selectedItem = settings.defaultMode
        configPanel.add(modeCombo, cgbc)

        cgbc.gridx = 0; cgbc.gridy = 3; cgbc.weightx = 0.0
        configPanel.add(JBLabel("Engine:").apply { toolTipText = "Container runtime engine" }, cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        engineCombo.selectedItem = settings.containerEngine
        configPanel.add(engineCombo, cgbc)

        cgbc.gridx = 0; cgbc.gridy = 4; cgbc.gridwidth = 2
        val checkboxPanel = JPanel(FlowLayout(FlowLayout.LEFT, 0, 0))
        checkboxPanel.add(autoSensitivityCheckbox)
        checkboxPanel.add(autonomousCheckbox)
        checkboxPanel.add(noSyncCheckbox)
        checkboxPanel.add(sqrapyardCheckbox)
        configPanel.add(checkboxPanel, cgbc)

        cgbc.gridx = 0; cgbc.gridy = 5; cgbc.gridwidth = 1; cgbc.weightx = 0.0
        configPanel.add(JBLabel("Qonstruction:").apply { toolTipText = "Optional build name" }, cgbc)
        cgbc.gridx = 1; cgbc.weightx = 1.0
        configPanel.add(qonstructionNameField, cgbc)

        configPanel.maximumSize = Dimension(Int.MAX_VALUE, configPanel.preferredSize.height)
        mainPanel.add(configPanel)
        mainPanel.add(Box.createVerticalStrut(8))

        // === ACTION BUTTONS (2 rows) ===
        val buttonPanel1 = JPanel(FlowLayout(FlowLayout.LEFT))
        buttonPanel1.add(runButton)
        buttonPanel1.add(deployButton)
        buttonPanel1.add(createTasqButton)
        buttonPanel1.add(aiConfigButton)
        buttonPanel1.add(initButton)
        buttonPanel1.add(resumeButton)
        buttonPanel1.add(openTasqButton)
        buttonPanel1.maximumSize = Dimension(Int.MAX_VALUE, buttonPanel1.preferredSize.height)
        mainPanel.add(buttonPanel1)

        val buttonPanel2 = JPanel(FlowLayout(FlowLayout.LEFT))
        buttonPanel2.add(cleanButton)
        buttonPanel2.add(cleanAllButton)
        buttonPanel2.add(refreshButton)
        buttonPanel2.maximumSize = Dimension(Int.MAX_VALUE, buttonPanel2.preferredSize.height)
        mainPanel.add(buttonPanel2)
        mainPanel.add(Box.createVerticalStrut(8))

        // === QAGE BROWSER WITH FULL ARTIFACT TREE ===
        val qagePanel = JPanel(BorderLayout())
        qagePanel.border = TitledBorder("Qages & Artifacts")

        // Custom renderer for qage list showing timestamp
        qageList.cellRenderer = object : DefaultListCellRenderer() {
            override fun getListCellRendererComponent(
                list: JList<*>?, value: Any?, index: Int, isSelected: Boolean, cellHasFocus: Boolean
            ): Component {
                val comp = super.getListCellRendererComponent(list, value, index, isSelected, cellHasFocus)
                if (value is QageListItem) {
                    text = "<html><b>${value.name}</b><br><small>${value.timestamp} • ${value.artifactCount} files</small></html>"
                }
                return comp
            }
        }
        qageList.fixedCellHeight = 40
        qageList.selectionMode = ListSelectionModel.SINGLE_SELECTION
        val qageScroll = JBScrollPane(qageList)
        qageScroll.preferredSize = Dimension(200, 140)

        // Artifact tree with expand/collapse
        artifactTree.isRootVisible = false
        artifactTree.showsRootHandles = true
        val treeScroll = JBScrollPane(artifactTree)
        treeScroll.preferredSize = Dimension(200, 200)

        // Buttons for qage actions
        val openFileButton = JButton("Open File")
        val revealButton = JButton("Reveal")
        val qageButtonPanel = JPanel(FlowLayout(FlowLayout.LEFT))
        qageButtonPanel.add(openFileButton)
        qageButtonPanel.add(revealButton)

        val qageDetailsPanel = JPanel(BorderLayout())
        qageDetailsPanel.add(JBLabel("Double-click file to open:"), BorderLayout.NORTH)
        qageDetailsPanel.add(treeScroll, BorderLayout.CENTER)
        qageDetailsPanel.add(qageButtonPanel, BorderLayout.SOUTH)

        val qageSplit = JSplitPane(JSplitPane.VERTICAL_SPLIT, qageScroll, qageDetailsPanel)
        qageSplit.resizeWeight = 0.3
        qagePanel.add(qageSplit, BorderLayout.CENTER)

        mainPanel.add(qagePanel)

        // Add to main
        val scrollPane = JBScrollPane(mainPanel)
        scrollPane.border = null
        add(scrollPane, BorderLayout.CENTER)

        // === EVENT HANDLERS ===
        qageList.addListSelectionListener {
            if (!it.valueIsAdjusting) {
                qageList.selectedValue?.let { qage -> loadArtifactTree(qage.name) }
            }
        }

        artifactTree.addMouseListener(object : java.awt.event.MouseAdapter() {
            override fun mouseClicked(e: java.awt.event.MouseEvent) {
                if (e.clickCount == 2) {
                    val node = artifactTree.lastSelectedPathComponent as? DefaultMutableTreeNode
                    val userObj = node?.userObject
                    if (userObj is ArtifactFile) {
                        openFileInEditor(userObj.path)
                    }
                }
            }
        })

        openFileButton.addActionListener {
            val node = artifactTree.lastSelectedPathComponent as? DefaultMutableTreeNode
            val userObj = node?.userObject
            if (userObj is ArtifactFile) {
                openFileInEditor(userObj.path)
            } else {
                service.notify("QonQrete", "Select a file in the tree", NotificationType.WARNING)
            }
        }

        revealButton.addActionListener {
            val selected = qageList.selectedValue
            if (selected != null) {
                val details = service.getQageDetails(selected.name)
                if (details != null) {
                    BrowserUtil.browse(File(details.path).toURI())
                }
            }
        }
    }

    private fun setupListeners() {
        runButton.addActionListener { executeRun() }
        deployButton.addActionListener { executeDeploy() }
        createTasqButton.addActionListener { executeCreateTasq() }
        aiConfigButton.addActionListener { executeAIConfig() }
        initButton.addActionListener { executeInit() }
        resumeButton.addActionListener { executeResume() }
        cleanButton.addActionListener { executeClean() }
        cleanAllButton.addActionListener { executeCleanAll() }
        openTasqButton.addActionListener { openTasqFile() }
        refreshButton.addActionListener { refreshState() }

        service.onRunStateChange { status ->
            ApplicationManager.getApplication().invokeLater { updateRunStatus(status) }
        }
        service.onShellStateChange { info ->
            ApplicationManager.getApplication().invokeLater { updateShellStatus(info) }
        }
        
        // Auto-refresh when run completes
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
        refreshQageList()
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
        val hasQages = qageListModel.size() > 0

        runButton.isEnabled = canRun && hasQonqrete && hasTasq && !isRunning
        initButton.isEnabled = canRun && hasQonqrete && !isRunning
        resumeButton.isEnabled = canRun && hasQonqrete && hasQages && !isRunning
        cleanButton.isEnabled = canRun && hasQonqrete && hasQages && !isRunning
        cleanAllButton.isEnabled = canRun && hasQonqrete && hasQages && !isRunning
        openTasqButton.isEnabled = hasQonqrete && hasTasq
        deployButton.isEnabled = !isRunning
        createTasqButton.isEnabled = !isRunning
        aiConfigButton.isEnabled = hasQonqrete && !isRunning
        refreshButton.isEnabled = !isRunning
        runButton.text = if (isRunning) "⏳ Running..." else "▶ Run Tasq"
    }

    private fun refreshQageList() {
        qageListModel.clear()
        artifactTreeRoot.removeAllChildren()
        artifactTreeModel.reload()

        service.getAvailableQages().forEach { qageName ->
            // Determine a human-friendly timestamp. For standard qages, use the formatted
            // timestamp derived from the name. For named qonstructions (parse returns null),
            // fall back to the last modified time of the directory. If both fail, just
            // display the name as the timestamp.
            val parsedTs = service.parseQageTimestamp(qageName)
            val timestamp: String = if (parsedTs != null) {
                service.formatQageTimestamp(qageName)
            } else {
                val details = service.getQageDetails(qageName)
                if (details != null) {
                    try {
                        val df = java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss")
                        df.format(java.util.Date(java.io.File(details.path).lastModified()))
                    } catch (_: Exception) {
                        qageName
                    }
                } else qageName
            }
            val details = service.getQageDetails(qageName)
            val artifactCount = details?.artifacts?.totalCount ?: 0
            qageListModel.addElement(QageListItem(qageName, timestamp, artifactCount))
        }
        if (qageListModel.size() > 0) {
            qageList.selectedIndex = 0
        }
    }

    // Data class for tree nodes
    private data class ArtifactFile(val name: String, val path: String) {
        override fun toString() = name
    }

    private fun loadArtifactTree(qageName: String) {
        artifactTreeRoot.removeAllChildren()

        val details = service.getQageDetails(qageName)
        if (details == null) {
            artifactTreeModel.reload()
            return
        }

        // Add each artifact category
        fun addCategory(name: String, files: List<String>, subdir: String) {
            if (files.isEmpty()) return
            val catNode = DefaultMutableTreeNode("$name (${files.size})")
            files.forEach { fileName ->
                // FIX: Handle config files at root level (empty subdir)
                val fullPath = if (subdir.isEmpty()) {
                    "${details.path}/$fileName"
                } else {
                    "${details.path}/$subdir/$fileName"
                }
                catNode.add(DefaultMutableTreeNode(ArtifactFile(fileName, fullPath)))
            }
            artifactTreeRoot.add(catNode)
        }

        addCategory("qodeyard", details.artifacts.qodeyard, "qodeyard")
        addCategory("exeq.d", details.artifacts.exeq, "exeq.d")
        addCategory("reqap.d", details.artifacts.reqap, "reqap.d")
        addCategory("briq.d", details.artifacts.briqs, "briq.d")
        addCategory("bloq.d", details.artifacts.bloqs, "bloq.d")
        addCategory("config", details.configFiles, "")

        artifactTreeModel.reload()

        // Expand all nodes
        for (i in 0 until artifactTree.rowCount) {
            artifactTree.expandRow(i)
        }

        // Automatically select the first category (typically qodeyard) so that the user
        // sees the generated code immediately. Row 0 is the (hidden) root, so select row 1
        // if available.
        if (artifactTree.rowCount > 1) {
            try {
                // Use the setter method instead of the property to avoid unresolved reference
                // errors on older Swing APIs. Row 0 is the hidden root; row 1 is the first
                // child (qodeyard). Selecting it immediately shows the code to the user.
                artifactTree.setSelectionRow(1)
            } catch (_: Exception) {
                // Ignore any selection errors – the tree will still display its nodes
            }
        }
    }

    private fun openFileInEditor(path: String) {
        val file = File(path)
        if (!file.exists()) {
            service.notify("QonQrete", "File not found: $path", NotificationType.WARNING)
            return
        }
        val vf = LocalFileSystem.getInstance().refreshAndFindFileByPath(path)
        if (vf != null) {
            FileEditorManager.getInstance(project).openFile(vf, true)
        }
    }
    
    private fun openTasqFile() {
        val tasqPath = service.getTasqPath()
        if (tasqPath != null && File(tasqPath).exists()) {
            openFileInEditor(tasqPath)
        } else {
            service.notify("QonQrete", "No default task file found", NotificationType.WARNING)
        }
    }

    private fun getConfigFromUI(): QonQreteRunConfig? {
        // Determine the final qonstruction name. First check the text field; if empty,
        // prompt the user for a name via dialog. Otherwise sanitize the provided name.
        val rawName = qonstructionNameField.text.trim()
        var finalName: String? = null

        if (rawName.isEmpty()) {
            // No name entered in the field. Prompt the user for a name. If the user
            // cancels the dialog, abort the configuration by returning null. When the
            // user provides a name, it will be sanitized within the dialog itself.
            val nameDialog = QonQreteQonstructionNameDialog(project, service)
            if (!nameDialog.showAndGet()) {
                return null
            }
            finalName = nameDialog.getQonstructionName()
        } else {
            // Sanitize the entered name and confirm if modifications are required
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
        if (!service.hasTasqFile()) { service.notify("QonQrete", "No default task file found. Use 'Create Task File' first.", NotificationType.WARNING); return }

        FileDocumentManager.getInstance().saveAllDocuments()

        // Auto-init if image is missing
        val initStatus = service.isInitialized()
        if (!initStatus.hasImage && initStatus.hasDockerfile) {
            val choice = Messages.showYesNoDialog(
                project,
                "Container image not built yet. Build it now?",
                "QonQrete: Init Required",
                Messages.getQuestionIcon()
            )
            if (choice != Messages.YES) return
            try {
                service.init()
                service.notify("QonQrete", "Building container image... Run Tasq again when init completes.", NotificationType.INFORMATION)
            } catch (e: Exception) {
                service.notify("QonQrete Error", "Init failed: ${e.message}", NotificationType.ERROR)
            }
            return
        }

        // Check for missing API keys
        val workingDir = service.getQonQreteWorkingDir()
        if (workingDir != null) {
            val configYaml = "$workingDir/worqspace/config.yaml"
            val missing = sh.qonqrete.intellij.actions.SetAIConfigAction.getMissingApiKeys(configYaml)
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
                    executeAIConfig()
                    return
                }
            }
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
        val action = com.intellij.openapi.actionSystem.ActionManager.getInstance()
            .getAction("QonQrete.DeployToWorkspace") ?: return
        val dataContext = com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.getDataContext(project)
        com.intellij.openapi.actionSystem.ex.ActionUtil.invokeAction(
            action,
            dataContext,
            com.intellij.openapi.actionSystem.ActionPlaces.UNKNOWN,
            null,
            null
        )
    }

    private fun executeCreateTasq() {
        val action = com.intellij.openapi.actionSystem.ActionManager.getInstance()
            .getAction("QonQrete.CreateTasq") ?: return
        val dataContext = com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.getDataContext(project)
        com.intellij.openapi.actionSystem.ex.ActionUtil.invokeAction(
            action,
            dataContext,
            com.intellij.openapi.actionSystem.ActionPlaces.UNKNOWN,
            null,
            null
        )
    }

    private fun executeAIConfig() {
        val action = com.intellij.openapi.actionSystem.ActionManager.getInstance()
            .getAction("QonQrete.SetAIConfig") ?: return
        val dataContext = com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT.getDataContext(project)
        com.intellij.openapi.actionSystem.ex.ActionUtil.invokeAction(
            action,
            dataContext,
            com.intellij.openapi.actionSystem.ActionPlaces.UNKNOWN,
            null,
            null
        )
    }

    private fun executeResume() {
        val selected = qageList.selectedValue
        if (selected == null) { service.notify("QonQrete", "Select a qage to resume", NotificationType.WARNING); return }
        try {
            val config = getConfigFromUI()
            service.resume(selected.name, config)
        } catch (e: Exception) { service.notify("QonQrete Error", e.message ?: "Unknown error", NotificationType.ERROR) }
    }

    private fun executeClean() {
        val selected = qageList.selectedValue
        if (selected == null) { service.notify("QonQrete", "Select a qage to clean", NotificationType.WARNING); return }
        val confirm = Messages.showYesNoDialog(project, "Delete qage '${selected.name}'?", "Confirm Clean", Messages.getWarningIcon())
        if (confirm != Messages.YES) return
        try { service.clean(qageName = selected.name); refreshQageList() }
        catch (e: Exception) { service.notify("QonQrete Error", e.message ?: "Unknown error", NotificationType.ERROR) }
    }
    
    private fun executeCleanAll() {
        val confirm = Messages.showYesNoDialog(
            project, 
            "Delete ALL qages?\n\nThis cannot be undone.", 
            "Confirm Clean All", 
            Messages.getWarningIcon()
        )
        if (confirm != Messages.YES) return
        try { service.clean(cleanAll = true); refreshQageList() }
        catch (e: Exception) { service.notify("QonQrete Error", e.message ?: "Unknown error", NotificationType.ERROR) }
    }
    
    override fun dispose() {
        refreshCallback?.let { service.removeRefreshListener(it) }
    }
}
