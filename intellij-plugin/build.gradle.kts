/**
 * QonQrete IntelliJ Plugin
 * Build configuration - Production Ready
 *
 * @author QonQrete
 * @version v1.4.7
 * @license Apache-2.0
 */

plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "2.1.20"
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
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit5:2.1.20")
    testImplementation("io.mockk:mockk:1.13.12")
}

java {
    sourceCompatibility = JavaVersion.VERSION_21
    targetCompatibility = JavaVersion.VERSION_21
}

intellij {
    version.set("2025.3")
    type.set("IC")
    plugins.set(listOf())
    updateSinceUntilBuild.set(false)
}

tasks {
    withType<JavaCompile> {
        sourceCompatibility = "21"
        targetCompatibility = "21"
    }

    withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_21)
        }
    }

    test {
        useJUnitPlatform()
    }

    patchPluginXml {
        changeNotes.set("""
            <h2>v${runtimeVersion} — 253+ Baseline, Zero-Warnings, VSCode Parity</h2>
            <ul>
                <li><b>Platform:</b> Raised IntelliJ baseline from 2023.3 (233) → 2025.3 (253). Java 17→21, Kotlin 1.9→2.0.21</li>
                <li><b>Zero warnings:</b> createFromInputEvent(), AnAction.update(), CredentialAttributes — all resolved</li>
                <li><b>Init fix:</b> Now runs .qonqrete/qonqrete.sh init from project root</li>
                <li><b>First-launch fix:</b> Setup wizard crash resolved (modal dialog)</li>
                <li><b>UX:</b> Qonstruction name only prompted when noSync enabled. Defaults match VSCode</li>
                <li><b>Providers:</b> Added mlx, llama-cpp. DeepSeek models 2→4 (thinking variants)</li>
                <li><b>Verified:</b> 0 warnings across full 9-version matrix (2023.3.8–2026.2 EAP)</li>
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
