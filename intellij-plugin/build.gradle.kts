/**
 * QonQrete IntelliJ Plugin
 * Build configuration - Production Ready
 *
 * @author QonQrete
 * @version v1.1.9
 * @license AGPL-3.0
 */

plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.21"
    id("org.jetbrains.intellij") version "1.17.3"
}

group = "sh.qonqrete"
version = "1.2.0"

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
    plugins.set(listOf("terminal"))
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
            <h2>1.2.0 - Workspace Deployment &amp; Hassle-Free Bootstrap</h2>
            <ul>
                <li><b>NEW:</b> "Deploy to Workspace" — one-click runtime install into any project (.qonqrete/)</li>
                <li><b>NEW:</b> "Create tasq.md" — starter template at project root</li>
                <li><b>NEW:</b> Auto-init on first run (builds container image automatically)</li>
                <li><b>NEW:</b> Root tasq.md sync — user-facing tasq at project root, auto-synced to runtime</li>
                <li><b>NEW:</b> .gitignore management — auto-adds .qonqrete/ on deploy</li>
                <li><b>NEW:</b> Versioned container images (qonqrete-qage:1.2.0)</li>
                <li><b>Improved:</b> Path discovery now checks .qonqrete/ first</li>
                <li><b>Improved:</b> Deploy-first UX flow when runtime not found</li>
                <li><b>Improved:</b> Identical behavior with VS Code extension</li>
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
    tasks {
        runPluginVerifier {
            ideVersions.set(listOf("2023.3", "2024.1"))
        }
    }
}
