// Top-level build file where you can add configuration options common to all sub-projects/modules.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.compose) apply false
    // Plugin de Firebase declarado pero NO aplicado a nivel raíz.
    // El módulo :app lo aplica condicionalmente solo si existe google-services.json (Fase 9 — Ing3).
    alias(libs.plugins.google.services) apply false
}