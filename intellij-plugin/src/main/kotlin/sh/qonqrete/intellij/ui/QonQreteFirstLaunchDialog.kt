/**
 * QonQrete First-Launch Provider Wizard
 * 3-step dialog: provider → model → API key
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.ui

import com.intellij.notification.NotificationType
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPasswordField
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.actions.SetAIConfigAction
import sh.qonqrete.intellij.services.QonQreteProjectService
import java.awt.BorderLayout
import java.awt.Dimension
import java.io.File
import javax.swing.*

/**
 * Data class for provider information
 */
data class ProviderInfo(
    val id: String,
    val label: String,
    val envKey: String,
    val models: List<String>,
    val notes: String = "",
    val configId: String = id
)

class QonQreteFirstLaunchDialog(private val project: Project) : DialogWrapper(project, true) {

    companion object {
        private val AI_AGENTS = listOf("qrystallizer", "instruqtor", "construqtor", "inspeqtor")

        private val PROVIDERS = listOf(
            ProviderInfo("openai", "OpenAI (API)", "OPENAI_API_KEY",
                listOf("gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini", "o3-mini", "o4-mini")),
            ProviderInfo("codex", "OpenAI Codex (CLI)", "OPENAI_API_KEY",
                listOf("gpt-5-codex", "gpt-5.5-codex-mini"), "Requires Codex CLI installed.", "openai"),
            ProviderInfo("google", "Google Gemini (API)", "GOOGLE_API_KEY",
                listOf("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"), "", "gemini"),
            ProviderInfo("gemini-cli", "Gemini CLI", "GOOGLE_API_KEY",
                listOf("gemini-2.5-pro", "gemini-2.5-flash"), "Requires Gemini CLI installed.", "gemini"),
            ProviderInfo("anthropic", "Anthropic (API)", "ANTHROPIC_API_KEY",
                listOf("claude-sonnet-4-20250514", "claude-haiku-4-5-20251001", "claude-opus-4-20250514")),
            ProviderInfo("claude-code", "Claude Code (CLI)", "ANTHROPIC_API_KEY",
                listOf("claude-sonnet-4-20250514", "claude-opus-4-20250514"), "Requires Claude Code CLI installed.", "anthropic"),
            ProviderInfo("deepseek", "DeepSeek (API)", "DEEPSEEK_API_KEY",
                listOf("deepseek-chat", "deepseek-reasoner")),
            ProviderInfo("codeseeq", "CodeSeeq (Codex CLI on DeepSeek)", "DEEPSEEK_API_KEY",
                listOf("deepseek-v4-flash", "deepseek-v4-flash-thinking", "deepseek-v4-pro", "deepseek-v4-pro-thinking"),
                "Requires CodeSeeq CLI + DEEPSEEK_API_KEY.", "codeseeq"),
            ProviderInfo("venice", "Venice (API)", "VENICE_API_KEY",
                listOf("deepseek-v3.2", "qwen3-coder-480b-a35b-instruct-turbo", "venice-uncensored", "llama-3.3-70b")),
            ProviderInfo("qwen", "Qwen (API)", "QWEN_API_KEY",
                listOf("qwen-plus", "qwen-turbo", "qwen-max")),
            ProviderInfo("openrouter", "OpenRouter (API)", "OPENROUTER_API_KEY",
                listOf("anthropic/claude-sonnet-4", "openai/gpt-4.1", "google/gemini-2.5-pro", "deepseek/deepseek-chat-v3")),
        )

        /**
         * Update config.yaml for all 4 agents with the chosen provider + model.
         */
        private fun updateConfigYaml(configPath: String, configProvider: String, model: String): Boolean {
            val file = File(configPath)
            if (!file.exists()) return false

            try {
                val lines = file.readLines().toMutableList()
                val result = mutableListOf<String>()
                var inAgent = false
                var providerSet = false
                var modelSet = false
                var currentAgent = ""

                for (line in lines) {
                    val agentMatch = Regex("^\\s{2}([a-z]+):\\s*$").find(line)
                    if (agentMatch != null && AI_AGENTS.contains(agentMatch.groupValues[1])) {
                        if (inAgent && !modelSet && model.isNotEmpty()) {
                            result.add("    model: $model")
                        }
                        currentAgent = agentMatch.groupValues[1]
                        inAgent = true
                        providerSet = false
                        modelSet = false
                        result.add(line)
                        continue
                    }

                    if (inAgent) {
                        if (Regex("^\\s{2}[a-z]+:\\s*$").containsMatchIn(line) &&
                            !Regex("^\\s{2}$currentAgent:\\s*$").containsMatchIn(line)) {
                            if (!modelSet && model.isNotEmpty()) {
                                result.add("    model: $model")
                            }
                            inAgent = false
                        }
                        if (inAgent && Regex("^\\s{4}provider:\\s*\\S+").containsMatchIn(line) && !providerSet) {
                            result.add("    provider: $configProvider")
                            providerSet = true
                            continue
                        }
                        if (inAgent && Regex("^\\s{4}model:\\s*\\S+").containsMatchIn(line) && !modelSet) {
                            if (model.isNotEmpty()) {
                                result.add("    model: $model")
                            }
                            modelSet = true
                            continue
                        }
                        if (Regex("^\\s{0,2}\\S").containsMatchIn(line) && !Regex("^\\s{4}").containsMatchIn(line)) {
                            if (inAgent && !modelSet && model.isNotEmpty()) {
                                result.add("    model: $model")
                            }
                            inAgent = false
                        }
                    }
                    result.add(line)
                }
                if (inAgent && !modelSet && model.isNotEmpty()) {
                    result.add("    model: $model")
                }

                file.writeText(result.joinToString("\n"))
                return true
            } catch (_: Exception) {
                return false
            }
        }
    }

    // UI components
    private val providerCombo = ComboBox(PROVIDERS.map { "${it.label}  ${if (it.notes.isNotEmpty()) "(${it.notes})" else ""}" }.toTypedArray())
    private val modelCombo = ComboBox<String>()
    private val customModelField = JBTextField(30)
    private val apiKeyField = JBPasswordField()
    private val envKeyLabel = JBLabel("")
    private val detectedKeyLabel = JBLabel("")

    private var selectedProvider: ProviderInfo = PROVIDERS[6] // Default: deepseek

    init {
        title = "QonQrete Setup — Configure Your AI Provider"
        isResizable = false

        // Default: select deepseek (index 6)
        providerCombo.selectedIndex = 6
        updateModelList()

        // Provider selection listener
        providerCombo.addActionListener {
            val idx = providerCombo.selectedIndex
            if (idx >= 0 && idx < PROVIDERS.size) {
                selectedProvider = PROVIDERS[idx]
                updateModelList()
                updateEnvKeyInfo()
            }
        }

        updateEnvKeyInfo()
    }

    private fun updateModelList() {
        modelCombo.removeAllItems()
        if (selectedProvider.models.isNotEmpty()) {
            selectedProvider.models.forEach { modelCombo.addItem(it) }
            modelCombo.addItem("Custom model name...")
            modelCombo.isEnabled = true
            customModelField.isEnabled = false
        } else {
            modelCombo.addItem("(optional — set in config.yaml)")
            modelCombo.isEnabled = false
            customModelField.isEnabled = true
            customModelField.text = ""
        }

        // Model selection listener
        modelCombo.removeActionListener(modelCombo.actionListeners.firstOrNull())
        modelCombo.addActionListener {
            val sel = modelCombo.selectedItem as? String
            customModelField.isEnabled = sel == "Custom model name..."
        }
    }

    private fun updateEnvKeyInfo() {
        val envKey = selectedProvider.envKey
        val existingKey = System.getenv(envKey) ?: SetAIConfigAction.getApiKey(envKey)

        if (!existingKey.isNullOrEmpty()) {
            val masked = if (existingKey.length > 12) {
                "${existingKey.take(8)}...${existingKey.takeLast(4)}"
            } else "****"
            detectedKeyLabel.text = "<html>🔍 Detected <b>$envKey</b>=$masked</html>"
        } else {
            detectedKeyLabel.text = ""
        }
        envKeyLabel.text = "<html><b>$envKey</b></html>"
    }

    override fun createCenterPanel(): JComponent {
        val builder = FormBuilder.createFormBuilder()

        // Step 1: Provider
        builder.addComponent(JBLabel("<html><b>Step 1/3: Select your AI provider</b></html>"))
        builder.addLabeledComponent("Provider:", providerCombo)
        builder.addSeparator()

        // Step 2: Model
        builder.addComponent(JBLabel("<html><b>Step 2/3: Select a model</b></html>"))
        builder.addLabeledComponent("Model:", modelCombo)
        builder.addLabeledComponent("Custom model:", customModelField)
        builder.addSeparator()

        // Step 3: API key
        builder.addComponent(JBLabel("<html><b>Step 3/3: API key</b></html>"))
        builder.addComponent(detectedKeyLabel)
        builder.addLabeledComponent(envKeyLabel, apiKeyField)

        val panel = JPanel(BorderLayout())
        panel.add(builder.panel, BorderLayout.NORTH)
        panel.border = JBUI.Borders.empty(15)
        panel.preferredSize = Dimension(550, 320)
        return panel
    }

    override fun doOKAction() {
        val provider = selectedProvider
        val model = if (customModelField.isEnabled && customModelField.text.isNotBlank()) {
            customModelField.text.trim()
        } else if (modelCombo.selectedItem is String && (modelCombo.selectedItem as String) != "Custom model name...") {
            modelCombo.selectedItem as String
        } else {
            ""
        }
        val apiKey = String(apiKeyField.password).trim()
        val envKey = provider.envKey

        // Store API key if entered
        if (apiKey.isNotEmpty()) {
            SetAIConfigAction.storeApiKey(envKey, apiKey)
            // Gemini/Google equivalence
            if (envKey == "GOOGLE_API_KEY") {
                SetAIConfigAction.storeApiKey("GEMINI_API_KEY", apiKey)
            }
        }

        // Determine config provider ID
        val configProvider = provider.configId.ifEmpty { provider.id }

        // Update config.yaml
        val service = QonQreteProjectService.getInstance(project)
        val workingDir = service.getQonQreteWorkingDir()
        if (workingDir != null) {
            val configPath = "$workingDir/worqspace/config.yaml"
            updateConfigYaml(configPath, configProvider, model)
        }

        // Add .qonqrete/ to .gitignore
        service.ensureGitignore()

        // Post-init notification showing how to start
        service.notify(
            "QonQrete",
            "✅ QonQrete is ready!\n\nProvider: ${provider.label}\nModel: ${model.ifEmpty { "default" }}\n\n" +
            "To start: open any .md file, right-click → \"Run as QonQrete Tasq\"\n" +
            "Or use: Tools → \"Run Tasq\" (uses default tasq.md)\n" +
            "Keyboard shortcut: Ctrl+Alt+Q",
            NotificationType.INFORMATION
        )

        super.doOKAction()
    }

    /**
     * Returns the chosen provider, model, and apiKey.
     */
    fun getSetupResult(): Triple<String, String, String> {
        val model = if (customModelField.isEnabled && customModelField.text.isNotBlank()) {
            customModelField.text.trim()
        } else if (modelCombo.selectedItem is String) {
            modelCombo.selectedItem as String
        } else ""
        return Triple(selectedProvider.id, model, String(apiKeyField.password).trim())
    }
}
