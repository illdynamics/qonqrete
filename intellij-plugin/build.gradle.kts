/**
 * QonQrete IntelliJ Plugin
 * Build configuration - Production Ready
 *
 * @author QonQrete
 * @version v1.4.6
 * @license Apache-2.0
 */

plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.21"
    id("org.jetbrains.intellij") version "1.17.3"
}

group = "sh.qonqrete"
val runtimeVersion = rootProject.file("../VERSION").readText().trim()
require(runtimeVersion.isNotBlank()) { "../VERSION is missing or empty" }
version = runtimeVersion

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.1")
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit5:1.9.21")
    testImplementation("io.mockk:mockk:1.13.8")
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

intellij {
    version.set("2023.3")
    type.set("IC")
    plugins.set(listOf())
    updateSinceUntilBuild.set(false)
}

tasks {
    withType<JavaCompile> {
        sourceCompatibility = "17"
        targetCompatibility = "17"
    }

    withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
        kotlinOptions.jvmTarget = "17"
    }

    test {
        useJUnitPlatform()
    }

    patchPluginXml {
        changeNotes.set("""
            <h2>v${runtimeVersion} — Plugin Verifier Zero-Warnings + DeepSeek V4</h2>
            <ul>
                <li><b>Fixed:</b> AnActionEvent constructor → createFromInputEvent() (scheduled for removal)</li>
                <li><b>Fixed:</b> beforeActionPerformedUpdate() → AnAction.update() (override-only violation)</li>
                <li><b>Fixed:</b> CredentialAttributes(serviceName, key) → 3-param constructor (deprecated, 2x)</li>
                <li><b>Fixed:</b> PluginManagerCore.getPlugin() → classloader plugin.xml read (internal API)</li>
                <li><b>Updated:</b> DeepSeek model names to V4 generation in AI config UI</li>
                <li><b>Verified:</b> 0 warnings across 2023.3.8–2026.2 EAP (9 IDE versions)</li>
            </ul>
        """.trimIndent())
    }

    signPlugin {
        certificateChain.set(System.getenv("CERTIFICATE_CHAIN"))
        privateKey.set(System.getenv("PRIVATE_KEY"))
        password.set(System.getenv("PRIVATE_KEY_PASSWORD"))
    }

    publishPlugin {
        token.set(System.getenv("PUBLISH_TOKEN"))
    }

    buildSearchableOptions {
        enabled = false
    }

    runPluginVerifier {
        // Exact versions matched to JetBrains Marketplace verifier (May 2026).
        // Run `./gradlew verifyPlugin` locally to reproduce Marketplace results
        // before uploading. The CI sed command rewrites this single-line listOf
        // per matrix runner — keep it on ONE LINE.
        ideVersions.set(listOf("2023.3.8", "2024.1.7", "2024.2.6", "2024.3.7.1", "2025.1.7.1", "2025.2.6.2", "2025.3.5", "2026.1.2", "2026.2-EAP-SNAPSHOT"))
    }
}
