/**
 * QonQrete v2 config helpers (provider + model only).
 *
 * The provider/model surface is read directly from config/providers.yaml so the
 * IDE never depends on a JSON parser being bundled at runtime.
 */
package sh.qonqrete.intellij.util

import com.intellij.openapi.project.Project
import sh.qonqrete.intellij.services.QonQreteSettingsState
import java.io.File

object QonQreteConfig {

    fun configPath(project: Project?): String? {
        val settings = QonQreteSettingsState.getInstance()
        if (settings.configPath.isNotBlank() && File(settings.configPath).exists()) return settings.configPath

        val qqSrc = System.getenv("QQ_SRC")
        if (!qqSrc.isNullOrBlank()) {
            val p = File(qqSrc, "config/qq.yaml")
            if (p.exists()) return p.absolutePath
        }

        val base = project?.basePath
        if (!base.isNullOrBlank()) {
            val p = File(base, "config/qq.yaml")
            if (p.exists()) return p.absolutePath
        }
        return settings.configPath.takeIf { it.isNotBlank() }
    }

    fun providersPath(project: Project?): String? {
        val settings = QonQreteSettingsState.getInstance()
        if (settings.providersPath.isNotBlank() && File(settings.providersPath).exists()) return settings.providersPath

        val qqSrc = System.getenv("QQ_SRC")
        if (!qqSrc.isNullOrBlank()) {
            val p = File(qqSrc, "config/providers.yaml")
            if (p.exists()) return p.absolutePath
        }

        val config = configPath(project)
        if (config != null) {
            val p = File(File(config).parentFile, "providers.yaml")
            if (p.exists()) return p.absolutePath
        }
        return settings.providersPath.takeIf { it.isNotBlank() }
    }

    data class Provider(val name: String, val models: List<String>)

    fun listProviders(project: Project?): List<Provider> {
        val path = providersPath(project) ?: return emptyList()
        val lines = runCatching { File(path).readLines() }.getOrElse { return emptyList() }
        val result = mutableListOf<Provider>()
        var current: String? = null
        var currentModels = mutableListOf<String>()

        fun flush() { if (current != null) result.add(Provider(current!!, currentModels.toList())) }

        for (line in lines) {
            val m = Regex("^  ([A-Za-z0-9_-]+):\\s*$").find(line)
            if (m != null) {
                flush()
                current = m.groupValues[1]
                currentModels = mutableListOf()
                continue
            }
            if (current != null) {
                val mm = Regex("^\\s{6}-\\s*(.+)\\s*$").find(line)
                if (mm != null) currentModels.add(mm.groupValues[1].trim())
            }
        }
        flush()
        return result
    }

    fun listModels(project: Project?, provider: String): List<String> {
        return listProviders(project).firstOrNull { it.name == provider }?.models ?: emptyList()
    }

    fun readProviderAndModel(project: Project?): Pair<String, String>? {
        val path = configPath(project) ?: return null
        val lines = runCatching { File(path).readLines() }.getOrElse { return null }
        val provider = lines.firstOrNull { it.trim().startsWith("provider:") }
            ?.substringAfter(":", "")?.trim()?.trim('\'', '"') ?: "codeseeq"

        var model = ""
        var inModels = false
        for (line in lines) {
            if (Regex("^\\s*models\\s*:\\s*$").matches(line)) { inModels = true; continue }
            if (inModels) {
                val m = Regex("^\\s{4}model\\s*:\\s*(.+)\\s*$").find(line)
                if (m != null && model.isEmpty()) { model = m.groupValues[1].trim().trim('\'', '"') }
                if (Regex("^\\S").matches(line)) inModels = false
            }
        }
        return provider to model
    }

    fun saveProviderAndModel(project: Project?, provider: String, model: String): Boolean {
        val path = configPath(project) ?: return false
        val file = File(path)
        if (!file.exists()) {
            file.parentFile?.mkdirs()
            file.writeText("provider: $provider\n\nmodels:\n  qlarifier:\n    model: $model\n  instruqtor:\n    model: $model\n  construqtor:\n    model: $model\n  inspeqtor:\n    model: $model\n")
            return true
        }

        val lines = file.readLines().toMutableList()
        var providerSet = false
        var inModels = false
        var currentRole = ""
        val roles = setOf("qlarifier", "instruqtor", "construqtor", "inspeqtor")
        val modelSetFor = mutableSetOf<String>()

        val result = mutableListOf<String>()
        for (line in lines) {
            if (!providerSet && Regex("^\\s*provider\\s*:").matches(line)) {
                result.add("provider: $provider")
                providerSet = true
                continue
            }
            if (Regex("^\\s*models\\s*:\\s*$").matches(line)) {
                inModels = true
                result.add(line)
                continue
            }
            if (inModels) {
                val roleMatch = Regex("^\\s{2}([A-Za-z0-9_]+)\\s*:\\s*$").find(line)
                if (roleMatch != null) {
                    currentRole = roleMatch.groupValues[1]
                    result.add(line)
                    continue
                }
                val modelMatch = Regex("^(\\s{4})model\\s*:.*$").find(line)
                if (modelMatch != null && roles.contains(currentRole)) {
                    result.add("${modelMatch.groupValues[1]}model: $model")
                    modelSetFor.add(currentRole)
                    continue
                }
                if (Regex("^\\S").matches(line)) { inModels = false; currentRole = "" }
            }
            result.add(line)
        }
        if (!providerSet) result.add(0, "provider: $provider")

        val missing = roles - modelSetFor
        if (missing.isNotEmpty()) {
            result.add("")
            if (result.none { Regex("^\\s*models\\s*:\\s*$").matches(it) }) result.add("models:")
            for (role in missing.sorted()) {
                result.add("  $role:")
                result.add("    model: $model")
            }
        }
        file.writeText(result.joinToString("\n"))
        return true
    }
}
