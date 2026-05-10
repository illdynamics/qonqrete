/**
 * QonQrete IntelliJ Plugin
 * Build configuration - Production Ready
 *
 * @author QonQrete
 * @version v1.4.5
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
            <h2>${runtimeVersion} - Plugin API Cleanup & Release Fixes</h2>
            <ul>
                <li><b>Fixed:</b> 10 deprecated API usages eliminated (8 ActionUtil.invokeAction, 2 CredentialAttributes)</li>
                <li><b>Fixed:</b> Verified compatible 2023.3.8–2026.2 EAP with zero warnings</li>
                <li><b>Added:</b> First-launch wizard auto-creates starter tasq.md</li>
                <li><b>Fixed:</b> Deploy action resolves runtime version from plugin version</li>
                <li><b>Cleanup:</b> All stale task files removed, only worqspace/tasq.md kept</li>
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
        ideVersions.set(listOf("2023.3", "2024.1"))
    }
}
