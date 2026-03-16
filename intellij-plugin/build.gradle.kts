/**
 * QonQrete IntelliJ Plugin
 * Build configuration - Production Ready
 *
 * @author WoNQ
 * @version 1.1.9
 * @license AGPL-3.0
 */

plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.21"
    id("org.jetbrains.intellij") version "1.17.2"
}

group = "sh.qonqrete"
version = "1.1.9"

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
        sinceBuild.set("233")
        untilBuild.set("243.*")
        changeNotes.set("""
            <h2>1.1.9 - Production Hardening Pass</h2>
            <ul>
                <li><b>Fixed:</b> Gradle wrapper now ships VALID jar (builds from clean checkout)</li>
                <li><b>Fixed:</b> Marker watcher uses daemon thread (proper JVM shutdown)</li>
                <li><b>Fixed:</b> Auto-refresh when run completes</li>
                <li><b>Fixed:</b> Status widget shows version + state</li>
                <li><b>Fixed:</b> Resume popup shows timestamps and artifact counts</li>
                <li><b>Added:</b> CommandBuilder utility for centralized command assembly</li>
                <li><b>Added:</b> QonQreteValidation utility for input validation</li>
                <li><b>Added:</b> ShellEscape utility for proper bash escaping</li>
                <li><b>Added:</b> "Clean All" button in tool window</li>
                <li><b>Added:</b> "Open Tasq" button for quick editing</li>
                <li><b>Added:</b> Tooltips on all config controls</li>
                <li><b>Added:</b> Qage timestamps in list display</li>
                <li><b>Added:</b> 40+ comprehensive unit tests</li>
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
}
