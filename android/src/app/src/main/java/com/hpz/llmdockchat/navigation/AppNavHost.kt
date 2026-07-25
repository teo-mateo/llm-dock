package com.hpz.llmdockchat.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.hpz.llmdockchat.core.AppContainer
import com.hpz.llmdockchat.feature.connect.ConnectScreen
import com.hpz.llmdockchat.feature.connect.ConnectViewModel
import com.hpz.llmdockchat.feature.home.HomeScreen
import com.hpz.llmdockchat.feature.home.HomeViewModel

/**
 * The app's navigation graph (Architecture D12). Connect is a destination like
 * any other rather than a modal in front of the app, so returning to it clears
 * the back stack — a back press from Connect leaves the app instead of walking
 * into a screen the session can no longer load.
 */
@Composable
fun AppNavHost(
    container: AppContainer,
    startDestination: String,
    modifier: Modifier = Modifier,
    navController: NavHostController = rememberNavController(),
) {
    // Raised only when silent re-authentication cannot succeed (F01-R6), and by
    // sign-out (F01-R7). Observed here, once, rather than in every screen —
    // that is the point of Architecture D4.
    val authenticationRequired by container.sessionState.authenticationRequired.collectAsState()
    LaunchedEffect(authenticationRequired) {
        if (authenticationRequired) navController.toConnect()
    }

    NavHost(
        navController = navController,
        startDestination = startDestination,
        modifier = modifier,
    ) {
        composable(Destinations.CONNECT) {
            val viewModel: ConnectViewModel = viewModel(
                factory = viewModelFactory {
                    initializer {
                        ConnectViewModel(
                            sessionManager = container.sessionManager,
                            reachability = container.reachabilityRepository,
                            serverUrlStore = container.serverUrlStore,
                            sessionState = container.sessionState,
                        )
                    }
                },
            )
            ConnectScreen(
                viewModel = viewModel,
                onSignedIn = {
                    navController.navigate(Destinations.HOME) {
                        popUpTo(Destinations.CONNECT) { inclusive = true }
                        launchSingleTop = true
                    }
                },
            )
        }

        composable(Destinations.HOME) {
            val viewModel: HomeViewModel = viewModel(
                factory = viewModelFactory {
                    initializer {
                        HomeViewModel(
                            authService = container.authService,
                            sessionManager = container.sessionManager,
                            serverUrlStore = container.serverUrlStore,
                        )
                    }
                },
            )
            // Sign-out also raises the session signal, so the effect above would
            // route here anyway; navigating directly keeps the transition
            // immediate rather than waiting a frame for the flow to settle.
            HomeScreen(viewModel = viewModel, onSignedOut = { navController.toConnect() })
        }
    }
}

private fun NavHostController.toConnect() {
    if (currentDestination?.route == Destinations.CONNECT) return
    navigate(Destinations.CONNECT) {
        popUpTo(graph.id) { inclusive = true }
        launchSingleTop = true
    }
}
