/**
 * QonQrete IntelliJ Plugin
 * Build configuration - Production Ready
 *
 * @author QonQrete
 * @version v1.4.0
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
            <h2>${runtimeVersion} - Runtime Truth/Streaming Alignment</h2>
            <ul>
                <li><b>Changed:</b> AI config UI targets primary runtime agents only (qrystallizer, instruqtor, construqtor, inspeqtor)</li>
                <li><b>Changed:</b> Default AI binding aligned to venice / deepseek-v3.2</li>
                <li><b>Changed:</b> Local-only providers (mlx, llama-cpp) hidden from shared provider picker</li>
                <li><b>Added:</b> Run-level no-sync control wired to launcher (--no-sync)</li>
                <li><b>Aligned:</b> Plugin docs/UI defaults match runtime-backed values (sensitivity=1, cycles=1, autonomous=true)</li>
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
