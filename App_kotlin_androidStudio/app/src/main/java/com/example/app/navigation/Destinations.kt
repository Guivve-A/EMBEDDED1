package com.example.app.navigation

sealed class Destination(val route: String, val title: String) {
    data object Splash : Destination("splash", "EMBEBIDOS")
    data object Dashboard : Destination("dashboard", "Inicio")
    data object Events : Destination("events", "Eventos")
    data object People : Destination("people", "Personas permitidas")
    data object Enroll : Destination("enroll", "Aprender Rostro")
    data object Settings : Destination("settings", "Ajustes")
}
