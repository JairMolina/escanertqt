plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}
val signingNames = listOf("TQT_ANDROID_KEYSTORE", "TQT_ANDROID_STORE_PASSWORD", "TQT_ANDROID_KEY_ALIAS", "TQT_ANDROID_KEY_PASSWORD")
val releaseReady = signingNames.all { !System.getenv(it).isNullOrBlank() }
android {
    namespace = "com.tqt.ota"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.tqt.ota"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    buildFeatures { compose = true; buildConfig = true }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    signingConfigs {
        if (releaseReady) create("privateDistribution") {
            storeFile = file(System.getenv(signingNames[0]))
            storePassword = System.getenv(signingNames[1])
            keyAlias = System.getenv(signingNames[2])
            keyPassword = System.getenv(signingNames[3])
        }
    }
    buildTypes {
        release { isMinifyEnabled = false; if (releaseReady) signingConfig = signingConfigs.getByName("privateDistribution") }
    }
    lint { abortOnError = true }
    testOptions { unitTests.isReturnDefaultValues = true }
}
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }
dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.02.01"))
    implementation("androidx.activity:activity-compose:1.12.4")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.work:work-runtime-ktx:2.11.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    debugImplementation("androidx.compose.ui:ui-tooling")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20251224")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation(platform("androidx.compose:compose-bom:2026.02.01"))
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
}
