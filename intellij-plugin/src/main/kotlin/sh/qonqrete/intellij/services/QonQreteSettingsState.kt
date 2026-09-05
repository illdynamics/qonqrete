/**
 * QonQrete v2 settings state.
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
        var qqPath: String = "",
        var configPath: String = "",
        var providersPath: String = "",
        var destinationDir: String = "",
        var noTui: Boolean = false
    )

    private var myState = State()

    companion object {
        @JvmStatic
        fun getInstance(): QonQreteSettingsState {
            return ApplicationManager.getApplication().getService(QonQreteSettingsState::class.java)
        }
    }

    override fun getState(): State = myState
    override fun loadState(state: State) { myState = state }

    var qqPath: String
        get() = myState.qqPath
        set(value) { myState.qqPath = value }

    var configPath: String
        get() = myState.configPath
        set(value) { myState.configPath = value }

    var providersPath: String
        get() = myState.providersPath
        set(value) { myState.providersPath = value }

    var destinationDir: String
        get() = myState.destinationDir
        set(value) { myState.destinationDir = value }

    var noTui: Boolean
        get() = myState.noTui
        set(value) { myState.noTui = value }
}

data class QonQreteRunConfig(
    val taskFile: String,
    val destinationDir: String,
    val noTui: Boolean = false
)

enum class RunState { IDLE, RUNNING, COMPLETED, FAILED }

data class RunStatus(
    val state: RunState = RunState.IDLE,
    val exitCode: Int? = null,
    val startTime: Long? = null,
    val endTime: Long? = null,
    val command: String? = null,
    val error: String? = null
)
