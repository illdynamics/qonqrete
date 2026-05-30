/**
 * Set AI Configuration Action
 * Configure providers, models, and API keys for QonQrete AI agents
 *
 * @author WoNQ
 * @version VERSION
 * @license Apache-2.0
 */

package sh.qonqrete.intellij.actions

import com.intellij.credentialStore.CredentialAttributes
import com.intellij.credentialStore.generateServiceName
import com.intellij.credentialStore.Credentials
import com.intellij.ide.passwordSafe.PasswordSafe
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import javax.swing.DefaultComboBoxModel
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.ui.Messages
import com.intellij.ui.components.JBLabel
import javax.swing.JPasswordField
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.FormBuilder
import com.intellij.util.ui.JBUI
import sh.qonqrete.intellij.services.QonQreteProjectService
import java.awt.BorderLayout
import java.awt.Dimension
import java.io.File
import javax.swing.*

class SetAIConfigAction : AnAction() {

    companion object {
        private val AI_AGENTS = listOf("qrystallizer", "instruqtor", "construqtor", "inspeqtor")

        private data class ProviderInfo(
            val label: String,
            val envKey: String,
            val models: List<String>
        )

        private val PROVIDERS = mapOf(
            "openai" to ProviderInfo("OpenAI", "OPENAI_API_KEY",
                listOf("gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "gpt-4o", "gpt-4o-mini", "o3-mini", "o4-mini")),
            "gemini" to ProviderInfo("Google Gemini (API)", "GOOGLE_API_KEY",
                listOf("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite")),
            "anthropic" to ProviderInfo("Anthropic", "ANTHROPIC_API_KEY",
                listOf("claude-sonnet-4-20250514", "claude-haiku-4-5-20251001", "claude-opus-4-20250514")),
            "deepseek" to ProviderInfo("DeepSeek", "DEEPSEEK_API_KEY",
                listOf("deepseek-v4-flash", "deepseek-v4-pro")),
            "qwen" to ProviderInfo("Qwen", "QWEN_API_KEY",
                listOf("qwen-plus", "qwen-turbo", "qwen-max")),
            "openrouter" to ProviderInfo("OpenRouter", "OPENROUTER_API_KEY",
                listOf("anthropic/claude-sonnet-4", "openai/gpt-4.1", "google/gemini-2.5-pro", "deepseek/deepseek-v4-flash")),
            // v1.3.12: Venice API (OpenAI-compatible). VENICE_API_KEY required, no fallback.
            "venice" to ProviderInfo("Venice", "VENICE_API_KEY",
                listOf(
                    "deepseek-v3.2",
                    "venice-uncensored",
                    "qwen3-coder-480b-a35b-instruct-turbo",
                    "qwen3-235b",
                    "qwen3-235b-a22b-instruct",
                    "qwen3-235b-a22b-thinking",
                    "qwen3-next-80b",
                    "qwen3-4b",
                    "qwen-2.5-qwq-32b",
                    "qwen-2.5-coder-32b",
                    "qwen-2.5-vl",
                    "mistral-31-24b",
                    "mistral-small-3.2-24b-instruct",
                    "llama-3.3-70b",
                    "llama-3.2-3b",
                    "llama-3.1-405b",
                    "dolphin-2.9.2-qwen2-72b",
                    "deepseek-r1-671b",
                    "deepseek-r1-llama-70b",
                    "deepseek-coder-v2-lite",
                    "claude-opus-4.6",
                    "claude-sonnet-4.6",
                    "glm-5",
                    "glm-4.7-flash-heretic",
                    "minimax-2.5"
                ))
        )

        /**
         * Store an API key using IntelliJ's PasswordSafe
         */
        fun storeApiKey(envKey: String, value: String) {
            val attrs = CredentialAttributes(generateServiceName("QonQrete", envKey), null)
            PasswordSafe.instance.set(attrs, Credentials(envKey, value))
        }

        /**
         * Retrieve an API key from PasswordSafe
         */
        fun getApiKey(envKey: String): String? {
            val attrs = CredentialAttributes(generateServiceName("QonQrete", envKey), null)
            return PasswordSafe.instance.getPassword(attrs)
        }

        /**
         * Build export string for terminal injection
         */
        fun buildApiKeyExports(): String {
            val exports = mutableListOf<String>()
            val keyMap = mapOf(
                "OPENAI_API_KEY" to "OPENAI_API_KEY",
                "GOOGLE_API_KEY" to "GOOGLE_API_KEY",
                "ANTHROPIC_API_KEY" to "ANTHROPIC_API_KEY",
                "OPENROUTER_API_KEY" to "OPENROUTER_API_KEY",
                "DEEPSEEK_API_KEY" to "DEEPSEEK_API_KEY",
                "QWEN_API_KEY" to "QWEN_API_KEY",
                "VENICE_API_KEY" to "VENICE_API_KEY"
            )
            for ((envKey, _) in keyMap) {
                // Env var takes priority, only inject from stored if env not set
                if (System.getenv(envKey).isNullOrEmpty()) {
                    val stored = getApiKey(envKey)
                    if (!stored.isNullOrEmpty()) {
                        val escaped = stored.replace("'", "'\\''")
                        exports.add("export $envKey='$escaped'")
                        if (envKey == "GOOGLE_API_KEY") {
                            exports.add("export GEMINI_API_KEY='$escaped'")
                        }
                    }
                }
            }
            return if (exports.isNotEmpty()) exports.joinToString(" && ") + " && " else ""
        }

        /**
         * Get required but missing API keys based on config.yaml
         */
        fun getMissingApiKeys(configPath: String): List<String> {
            val configs = readAgentConfigs(configPath)
            val providers = configs.values.map { it.first }.filter { it != "local" }.toSet()
            return providers.mapNotNull { PROVIDERS[it]?.envKey }
                .distinct()
                .filter { envKey -> !hasApiKeyAvailable(envKey) }
        }

        /**
         * Check if an API key is available via env var OR PasswordSafe.
         * Handles GOOGLE_API_KEY / GEMINI_API_KEY equivalence.
         */
        private fun hasApiKeyAvailable(envKey: String): Boolean {
            // Check real env var
            if (!System.getenv(envKey).isNullOrEmpty()) return true
            // Gemini/Google equivalence
            if (envKey == "GOOGLE_API_KEY" && !System.getenv("GEMINI_API_KEY").isNullOrEmpty()) return true
            if (envKey == "GEMINI_API_KEY" && !System.getenv("GOOGLE_API_KEY").isNullOrEmpty()) return true
            // Check PasswordSafe
            if (!getApiKey(envKey).isNullOrEmpty()) return true
            // Gemini/Google equivalence in store
            if (envKey == "GOOGLE_API_KEY" && !getApiKey("GEMINI_API_KEY").isNullOrEmpty()) return true
            return false
        }

        private data class AgentConfig(val provider: String, val model: String)

        private fun readAgentConfigs(configPath: String): Map<String, Pair<String, String>> {
            val defaults = mutableMapOf(
                "qrystallizer" to Pair("venice", "deepseek-v3.2"),
                "instruqtor" to Pair("venice", "deepseek-v3.2"),
                "construqtor" to Pair("venice", "deepseek-v3.2"),
                "inspeqtor" to Pair("venice", "deepseek-v3.2")
            )
            val file = File(configPath)
            if (!file.exists()) return defaults

            try {
                val lines = file.readLines()
                var currentAgent: String? = null
                for (line in lines) {
                    val agentMatch = Regex("^\\s{2}(\\w+):\\s*$").find(line)
                    if (agentMatch != null) {
                        val name = agentMatch.groupValues[1]
                        currentAgent = if (name in AI_AGENTS) name else null
                        if (currentAgent != null) {
                            defaults[currentAgent!!] = defaults[currentAgent!!]!!.copy(second = "") // Reset to catch if present
                        }
                        continue
                    }
                    if (currentAgent != null) {
                        val provMatch = Regex("^\\s{4}provider:\\s*(\\S+)").find(line)
                        if (provMatch != null) {
                            defaults[currentAgent!!] = defaults[currentAgent!!]!!.copy(first = provMatch.groupValues[1])
                            continue
                        }
                        val modelMatch = Regex("^\\s{4}model:\\s*(\\S+)").find(line)
                        if (modelMatch != null) {
                            defaults[currentAgent!!] = defaults[currentAgent!!]!!.copy(second = modelMatch.groupValues[1])
                            continue
                        }
                        if (Regex("^\\s{0,2}\\S").containsMatchIn(line)) currentAgent = null
                    }
                }
            } catch (_: Exception) {}
            return defaults
        }

        private fun writeAgentConfig(configPath: String, agent: String, provider: String, model: String): Boolean {
            val file = File(configPath)
            if (!file.exists()) return false
            try {
                val lines = file.readLines().toMutableList()
                var inAgent = false
                var providerSet = false
                var modelSet = false
                val result = mutableListOf<String>()
                
                for (i in lines.indices) {
                    val line = lines[i]
                    if (Regex("^\\s{2}$agent:\\s*$").containsMatchIn(line)) {
                        inAgent = true; providerSet = false; modelSet = false
                        result.add(line)
                        continue
                    }
                    
                    if (inAgent) {
                        if (Regex("^\\s{2}\\w+:\\s*$").containsMatchIn(line)) {
                            if (!modelSet && model.isNotEmpty()) {
                                result.add("    model: $model")
                            }
                            inAgent = false
                        } else if (Regex("^\\s{4}provider:\\s*\\S+").containsMatchIn(line)) {
                            result.add("    provider: $provider")
                            providerSet = true
                            continue
                        } else if (Regex("^\\s{4}model:\\s*\\S+").containsMatchIn(line)) {
                            if (model.isNotEmpty()) {
                                result.add("    model: $model")
                            }
                            modelSet = true
                            continue
                        } else if (Regex("^\\s{0,2}\\S").containsMatchIn(line)) {
                            if (!modelSet && model.isNotEmpty()) {
                                result.add("    model: $model")
                            }
                            inAgent = false
                        }
                    }
                    result.add(line)
                }
                file.writeText(result.joinToString("\n"))
                return true
            } catch (_: Exception) { return false }
        }
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val service = QonQreteProjectService.getInstance(project)
        val workingDir = service.getQonQreteWorkingDir()

        if (workingDir == null) {
            Messages.showErrorDialog(project, "QonQrete runtime not found. Deploy first.", "QonQrete")
            return
        }

        val configPath = "$workingDir/worqspace/config.yaml"
        if (!File(configPath).exists()) {
            Messages.showErrorDialog(project, "config.yaml not found in runtime.", "QonQrete")
            return
        }

        val dialog = AIConfigDialog(project, configPath)
        if (dialog.showAndGet()) {
            service.notify("QonQrete", "AI configuration updated.", NotificationType.INFORMATION)
        }
    }

    override fun update(e: AnActionEvent) {
        val project = e.project
        e.presentation.isEnabledAndVisible = project != null &&
            QonQreteProjectService.getInstance(project).getQonQretePath() != null
    }

    /**
     * Full AI configuration dialog
     */
    private class AIConfigDialog(
        private val project: Project,
        private val configPath: String
    ) : DialogWrapper(project) {

        private data class AgentRow(
            val providerCombo: ComboBox<String>,
            val modelField: JBTextField
        )

        private val agentRows = mutableMapOf<String, AgentRow>()
        private val apiKeyFields = mutableMapOf<String, JPasswordField>()

        init {
            title = "QonQrete: AI Configuration"
            init()
        }

        override fun createCenterPanel(): JComponent {
            val configs = readAgentConfigs(configPath)
            val providerIds = PROVIDERS.keys.toList()

            val builder = FormBuilder.createFormBuilder()
            builder.addComponent(JBLabel("<html><b>Agent Providers & Models</b></html>"))
            builder.addSeparator()

            for (agent in AI_AGENTS) {
                val (currentProv, currentModel) = configs[agent] ?: Pair("deepseek", "deepseek-v4-flash")

                val providerCombo = ComboBox(DefaultComboBoxModel(providerIds.toTypedArray()))
                providerCombo.selectedItem = currentProv
                providerCombo.renderer = object : DefaultListCellRenderer() {
                    override fun getListCellRendererComponent(list: JList<*>?, value: Any?, index: Int, isSelected: Boolean, cellHasFocus: Boolean) =
                        super.getListCellRendererComponent(list, PROVIDERS[value]?.label ?: value, index, isSelected, cellHasFocus)
                }

                val modelField = JBTextField(currentModel, 25)
                modelField.toolTipText = "Model name for $agent"

                // Update model suggestions when provider changes
                providerCombo.addActionListener {
                    val prov = providerCombo.selectedItem as? String ?: return@addActionListener
                    val models = PROVIDERS[prov]?.models ?: return@addActionListener
                    if (modelField.text.isEmpty() || PROVIDERS.values.any { it.models.contains(modelField.text) }) {
                        modelField.text = models.firstOrNull() ?: ""
                    }
                }

                val row = JPanel(BorderLayout(4, 0))
                row.add(providerCombo, BorderLayout.WEST)
                row.add(modelField, BorderLayout.CENTER)

                builder.addLabeledComponent("$agent:", row)
                agentRows[agent] = AgentRow(providerCombo, modelField)
            }

            builder.addSeparator()
            builder.addComponent(JBLabel("<html><b>API Keys</b> (stored securely in IntelliJ credential store)</html>"))

            for ((_, info) in PROVIDERS) {
                val existing = getApiKey(info.envKey)
                val envSet = !System.getenv(info.envKey).isNullOrEmpty()
                val field = JPasswordField()
                if (!existing.isNullOrEmpty()) {
                    field.text = existing
                }
                val hint = if (envSet) " (env var set)" else ""
                builder.addLabeledComponent("${info.label}$hint:", field)
                apiKeyFields[info.envKey] = field
            }

            val panel = JPanel(BorderLayout())
            panel.add(builder.panel, BorderLayout.NORTH)
            panel.border = JBUI.Borders.empty(10)
            panel.preferredSize = Dimension(550, 450)
            return panel
        }

        override fun doOKAction() {
            // Save agent configs
            for (agent in AI_AGENTS) {
                val row = agentRows[agent] ?: continue
                val provider = row.providerCombo.selectedItem as? String ?: continue
                val model = row.modelField.text.trim()
                writeAgentConfig(configPath, agent, provider, model)
            }

            // Save API keys
            for ((envKey, field) in apiKeyFields) {
                val value = String(field.password).trim()
                if (value.isNotEmpty()) {
                    storeApiKey(envKey, value)
                }
            }

            super.doOKAction()
        }
    }
}
