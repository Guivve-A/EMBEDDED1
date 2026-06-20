package com.example.app.navigation

import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.app.ui.screens.DashboardScreen
import com.example.app.ui.screens.EnrollScreen
import com.example.app.ui.screens.EventsScreen
import com.example.app.ui.screens.PeopleScreen
import com.example.app.ui.screens.SettingsScreen
import com.example.app.ui.screens.SplashScreen

@Composable
fun AppNavGraph(
    modifier: Modifier = Modifier,
    // Si la app se abrió desde el tap de una notificación FCM, salta directo a Eventos.
    deeplinkToEvents: Boolean = false,
) {
    val navController = rememberNavController()
    val anim = tween<Float>(durationMillis = 220)

    LaunchedEffect(deeplinkToEvents) {
        if (deeplinkToEvents) {
            navController.navigate(Destination.Events.route) {
                popUpTo(Destination.Splash.route) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    NavHost(
        navController = navController,
        startDestination = Destination.Splash.route,
        modifier = modifier,
        enterTransition = { fadeIn(animationSpec = anim) + slideInHorizontally(initialOffsetX = { it / 24 }) },
        exitTransition = { fadeOut(animationSpec = anim) + slideOutHorizontally(targetOffsetX = { -it / 24 }) },
        popEnterTransition = { fadeIn(animationSpec = anim) + slideInHorizontally(initialOffsetX = { -it / 24 }) },
        popExitTransition = { fadeOut(animationSpec = anim) + slideOutHorizontally(targetOffsetX = { it / 24 }) },
    ) {
        composable(Destination.Splash.route) {
            SplashScreen(
                onNavigateDashboard = {
                    navController.navigate(Destination.Dashboard.route) {
                        popUpTo(Destination.Splash.route) { inclusive = true }
                    }
                },
            )
        }
        composable(Destination.Dashboard.route) {
            DashboardScreen(
                onNavigate = { dest -> navController.navigate(dest.route) },
            )
        }
        composable(Destination.Events.route) {
            EventsScreen(onBack = { navController.popBackStack() })
        }
        composable(Destination.People.route) {
            PeopleScreen(
                onBack = { navController.popBackStack() },
                onEnroll = { navController.navigate(Destination.Enroll.route) },
            )
        }
        composable(Destination.Enroll.route) {
            EnrollScreen(onBack = { navController.popBackStack() })
        }
        composable(Destination.Settings.route) {
            SettingsScreen(onBack = { navController.popBackStack() })
        }
    }
}
