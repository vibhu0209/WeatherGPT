plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
}

/**
 * The single source of truth for the backend address. Override per machine without editing code:
 *
 *   gradlew installDebug -Pweathergpt.apiUrl=http://192.168.1.10:8000/
 *
 * or put `weathergpt.apiUrl=...` in `local.properties` / `~/.gradle/gradle.properties`.
 * The backend address is not a secret, so BuildConfig is the right home for it.
 *
 * Default is the Android emulator's alias for the host machine. `localhost` inside an emulator
 * is the emulator itself, so it can never reach a backend running on Windows.
 */
fun apiUrl(property: String, fallback: String): String {
    val value = (project.findProperty(property) as String?)?.trim().orEmpty().ifEmpty { fallback }
    // Retrofit resolves endpoint paths relative to the base URL and throws at build time if the
    // base does not end in '/'. Failing here names the property instead of crashing at startup.
    require(value.endsWith("/")) { "$property must end with '/' (Retrofit base URL rule), got: $value" }
    return value
}

val debugApiUrl = apiUrl("weathergpt.apiUrl", "http://10.0.2.2:8000/")
val releaseApiUrl = apiUrl("weathergpt.releaseApiUrl", "https://localhost/")
android {
    namespace = "in.weathergpt"
    compileSdk { version = release(37) { minorApiLevel = 0 } }
    defaultConfig {
        applicationId = "in.weathergpt"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    buildFeatures { compose = true; buildConfig = true }
    bundle { language { enableSplit = false } }
    lint { disable += "MissingTranslation" }
    buildTypes {
        debug { buildConfigField("String", "API_URL", "\"$debugApiUrl\"") }
        release { buildConfigField("String", "API_URL", "\"$releaseApiUrl\"") }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }
dependencies {
    implementation(platform("androidx.compose:compose-bom:2025.08.01"))
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.2")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.2")
    implementation("androidx.appcompat:appcompat:1.7.1")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.room:room-runtime:2.7.2")
    implementation("androidx.room:room-ktx:2.7.2")
    ksp("androidx.room:room-compiler:2.7.2")
    implementation("androidx.datastore:datastore-preferences:1.1.7")
    implementation("androidx.work:work-runtime-ktx:2.10.3")
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
}

android.sourceSets.getByName("test").resources.directories.add("../../contracts")

