/**
 * QonQrete Settings State
 * Persistent application settings with all configuration options
 *
 * @author WoNQ
 * @version VERSION
 * @license AGPL-3.0
 */

package sh.qonqrete.intellij.services

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage

@State(
    name = "QonQreteSettings",
    storages = [Storage("qonqrete.xml")]
)
@Service(Service.Level.APP)
class QonQreteSettingsState : PersistentStateComponent<QonQreteSettingsState.State> {

    data class State(
        var defaultSensitivity: Int = 1,
        var defaultAutoBriqSensitivity: Boolean = false,
        var defaultCycles: Int = 1,
        var defaultMode: String = "program",
        var defaultAutonomous: Boolean = true,
        var noSync: Boolean = false,
        var useSqrapyard: Boolean = false,
        var containerEngine: String = "auto",
        var customQonqretePath: String = "",
        var customBashPath: String = "",
        var autoOpenToolWindowOnRun: Boolean = true,
        var qageListLimit: Int = 10,
        var markerTimeoutMinutes: Int = 60,
        var welcomeShown: Boolean = false
    )

    private var myState = State()

    companion object {
        @JvmStatic
        fun getInstance(): QonQreteSettingsState {
            return ApplicationManager.getApplication().getService(QonQreteSettingsState::class.java)
        }
    }

    override fun getState(): State = myState

    override fun loadState(state: State) {
        myState = state
    }

    // Convenience accessors with validation
    var defaultSensitivity: Int
        get() = myState.defaultSensitivity
        set(value) { myState.defaultSensitivity = value.coerceIn(0, 16) }

    var defaultAutoBriqSensitivity: Boolean
        get() = myState.defaultAutoBriqSensitivity
        set(value) { myState.defaultAutoBriqSensitivity = value }

    var defaultCycles: Int
        get() = myState.defaultCycles
        set(value) { myState.defaultCycles = value.coerceIn(1, 50) }

    var defaultMode: String
        get() = myState.defaultMode
        set(value) { myState.defaultMode = value }

    var defaultAutonomous: Boolean
        get() = myState.defaultAutonomous
        set(value) { myState.defaultAutonomous = value }

    var noSync: Boolean
        get() = myState.noSync
        set(value) { myState.noSync = value }

    var useSqrapyard: Boolean
        get() = myState.useSqrapyard
        set(value) { myState.useSqrapyard = value }

    var containerEngine: String
        get() = myState.containerEngine
        set(value) { myState.containerEngine = value }

    var customQonqretePath: String
        get() = myState.customQonqretePath
        set(value) { myState.customQonqretePath = value }

    var customBashPath: String
        get() = myState.customBashPath
        set(value) { myState.customBashPath = value }

    var autoOpenToolWindowOnRun: Boolean
        get() = myState.autoOpenToolWindowOnRun
        set(value) { myState.autoOpenToolWindowOnRun = value }

    var qageListLimit: Int
        get() = myState.qageListLimit
        set(value) { myState.qageListLimit = value.coerceIn(1, 100) }

    var markerTimeoutMinutes: Int
        get() = myState.markerTimeoutMinutes
        set(value) { myState.markerTimeoutMinutes = value.coerceIn(1, 240) }

    var welcomeShown: Boolean
        get() = myState.welcomeShown
        set(value) { myState.welcomeShown = value }
}

/**
 * Run configuration for QonQrete
 */
data class QonQreteRunConfig(
    val sensitivity: Int = 1,
    val autoSensitivity: Boolean = false,
    val cycles: Int = 1,
    val mode: String = "program",
    val autonomous: Boolean = true,
    val noSync: Boolean = false,
    val qonstructionName: String? = null,
    val useSqrapyard: Boolean = false,
    val containerEngine: String = "auto"
) {
    companion object {
        fun fromSettings(): QonQreteRunConfig {
            val settings = QonQreteSettingsState.getInstance()
            return QonQreteRunConfig(
                sensitivity = settings.defaultSensitivity,
                autoSensitivity = settings.defaultAutoBriqSensitivity,
                cycles = settings.defaultCycles,
                mode = settings.defaultMode,
                autonomous = settings.defaultAutonomous,
                noSync = settings.noSync,
                useSqrapyard = settings.useSqrapyard,
                containerEngine = settings.containerEngine
            )
        }
    }
}

/**
 * Sanitization result
 */
data class SanitizeResult(
    val original: String,
    val sanitized: String,
    val wasModified: Boolean
)

/**
 * Shell state enum - explicit states for honest tracking
 */
enum class ShellState {
    NO_BASH,      // No bash found
    VERIFYING,    // Verification in progress
    READY,        // Verified and ready
    SHELL_ERROR   // Verification failed
}

/**
 * Shell information
 */
data class ShellInfo(
    val shellPath: String,
    val isWindows: Boolean,
    val hasBash: Boolean,
    val shellType: String,
    var state: ShellState = if (hasBash) ShellState.VERIFYING else ShellState.NO_BASH,
    var verificationError: String? = null
) {
    val isReady: Boolean get() = state == ShellState.READY
}

/**
 * Run state enum
 */
enum class RunState {
    IDLE, RUNNING, COMPLETED, FAILED, TIMEOUT
}

/**
 * Run status data
 */
data class RunStatus(
    val state: RunState = RunState.IDLE,
    val exitCode: Int? = null,
    val startTime: Long? = null,
    val endTime: Long? = null,
    val command: String? = null,
    val error: String? = null
)

/**
 * Initialization status
 */
data class InitStatus(
    val hasDockerfile: Boolean,
    val hasImage: Boolean,
    val engine: String?
)

/**
 * Qage details
 */
data class QageDetails(
    val name: String,
    val path: String,
    val timestamp: Long?,
    val artifacts: QageArtifacts,
    val configFiles: List<String>
)

data class QageArtifacts(
    val qodeyard: List<String>,
    val exeq: List<String>,
    val reqap: List<String>,
    val briqs: List<String>,
    val bloqs: List<String>
) {
    val totalCount: Int get() = qodeyard.size + exeq.size + reqap.size + briqs.size + bloqs.size
}
