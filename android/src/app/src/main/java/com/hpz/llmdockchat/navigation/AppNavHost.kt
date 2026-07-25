package com.hpz.llmdockchat.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.navigation
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.hpz.llmdockchat.core.AppContainer
import com.hpz.llmdockchat.core.ui.theme.LlmTheme
import com.hpz.llmdockchat.feature.connect.ConnectScreen
import com.hpz.llmdockchat.feature.connect.ConnectViewModel
import com.hpz.llmdockchat.feature.conversations.ConversationListScreen
import com.hpz.llmdockchat.feature.conversations.ConversationListViewModel
import com.hpz.llmdockchat.feature.models.ModelDetailScreen
import com.hpz.llmdockchat.feature.models.ModelDetailViewModel
import com.hpz.llmdockchat.feature.models.ModelsScreen
import com.hpz.llmdockchat.feature.models.ModelsViewModel
import com.hpz.llmdockchat.feature.newchat.NewChatScreen
import com.hpz.llmdockchat.feature.newchat.NewChatViewModel
import com.hpz.llmdockchat.feature.thread.ThreadScreen
import com.hpz.llmdockchat.feature.thread.ThreadViewModel

/**
 * The app's navigation graph (Architecture D12). Connect is a destination like
 * any other rather than a modal in front of the app, so returning to it clears
 * the back stack — a back press from Connect leaves the app instead of walking
 * into a screen the session can no longer load.
 *
 * [Destinations.CHATS] and [Destinations.MODELS] live in the nested
 * [Destinations.TABS] graph and share [AppBottomBar]; [Destinations.THREAD]
 * and [Destinations.NEW_CHAT] are pushed on top of it without one (F02-R7).
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
                    navController.navigate(Destinations.TABS) {
                        popUpTo(Destinations.CONNECT) { inclusive = true }
                        launchSingleTop = true
                    }
                },
            )
        }

        navigation(startDestination = Destinations.CHATS, route = Destinations.TABS) {
            composable(Destinations.CHATS) { backStackEntry ->
                TabScaffold(navController) {
                    val viewModel: ConversationListViewModel = viewModel(
                        factory = viewModelFactory {
                            initializer { ConversationListViewModel(container.conversationsRepository) }
                        },
                    )
                    ConversationListScreen(
                        viewModel = viewModel,
                        onOpenConversation = { conversation ->
                            navController.navigate(Destinations.thread(conversation.id))
                        },
                        onNewConversation = { navController.navigate(Destinations.newChat()) },
                    )
                }
            }

            composable(Destinations.MODELS) {
                TabScaffold(navController) {
                    val viewModel: ModelsViewModel = viewModel(
                        factory = viewModelFactory {
                            initializer {
                                ModelsViewModel(
                                    servicesRepository = container.servicesRepository,
                                    servicesStreamRepository = container.servicesStreamRepository,
                                    gpuStreamRepository = container.gpuStreamRepository,
                                )
                            }
                        },
                    )
                    ModelsScreen(
                        viewModel = viewModel,
                        onNewChatFromModel = { serviceName ->
                            navController.navigate(Destinations.newChatWithService(serviceName))
                        },
                        onOpenDetail = { serviceName ->
                            navController.navigate(Destinations.modelDetail(serviceName))
                        },
                    )
                }
            }
        }

        composable(Destinations.MODEL_DETAIL) { backStackEntry ->
            val serviceName = backStackEntry.arguments?.getString("serviceName").orEmpty()
            val viewModel: ModelDetailViewModel = viewModel(
                // Keyed by service so opening a second model's detail from the
                // first (via Back then a different row) never shares state,
                // same reasoning as THREAD's key.
                key = "model_detail_$serviceName",
                factory = viewModelFactory {
                    initializer {
                        ModelDetailViewModel(
                            serviceName = serviceName,
                            servicesRepository = container.servicesRepository,
                            servicesStreamRepository = container.servicesStreamRepository,
                        )
                    }
                },
            )
            ModelDetailScreen(viewModel = viewModel, onBack = { navController.popBackStack() })
        }

        composable(Destinations.THREAD) { backStackEntry ->
            val conversationId = backStackEntry.arguments?.getString("conversationId").orEmpty()
            val viewModel: ThreadViewModel = viewModel(
                // Keyed by conversation so two threads visited in a row never
                // share a ViewModel — and so its stream, which is scoped to
                // this destination, dies with the destination (Architecture D5).
                key = "thread_$conversationId",
                factory = viewModelFactory {
                    initializer {
                        ThreadViewModel(
                            conversationId = conversationId,
                            repository = container.chatRepository,
                            drafts = container.draftStore,
                            servicesStreamRepository = container.servicesStreamRepository,
                            openRouterModelsRepository = container.openRouterModelsRepository,
                            conversationsRepository = container.conversationsRepository,
                            mcpServersRepository = container.mcpServersRepository,
                        )
                    }
                },
            )
            ThreadScreen(viewModel = viewModel, onBack = { navController.popBackStack() })
        }

        composable(
            Destinations.NEW_CHAT,
            arguments = listOf(navArgument("service") { type = NavType.StringType; nullable = true; defaultValue = null }),
        ) { backStackEntry ->
            val preselectedServiceName = backStackEntry.arguments?.getString("service")
            val viewModel: NewChatViewModel = viewModel(
                factory = viewModelFactory {
                    initializer {
                        NewChatViewModel(
                            servicesRepository = container.servicesRepository,
                            promptsRepository = container.promptsRepository,
                            mcpServersRepository = container.mcpServersRepository,
                            openRouterModelsRepository = container.openRouterModelsRepository,
                            conversationsRepository = container.conversationsRepository,
                            preferences = container.newChatPreferences,
                            servicesStreamRepository = container.servicesStreamRepository,
                            preselectedServiceName = preselectedServiceName,
                        )
                    }
                },
            )
            NewChatScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onConversationCreated = { id ->
                    // Replaces the sheet on the back stack — Back from the new
                    // thread returns to the conversation list, not to a sheet
                    // for a chat that already exists.
                    navController.navigate(Destinations.thread(id)) {
                        popUpTo(Destinations.NEW_CHAT) { inclusive = true }
                    }
                },
            )
        }
    }
}

/**
 * Wraps a tab's content in the shared bottom bar (F02-R7). Tab switches
 * `popUpTo` [Destinations.CHATS] — the [Destinations.TABS] graph's own,
 * fixed start route, not the outer [NavHost]'s (which may be Connect) — with
 * `saveState`/`restoreState`, the standard bottom-nav idiom: each tab's
 * ViewModel and `rememberSaveable` state (including scroll position) survive
 * switching away and back.
 *
 * Insets (fix pass A2): this Scaffold applies none of its own
 * ([WindowInsets] of zero) — [AppBottomBar] is a `NavigationBar`, which pads
 * itself clear of the navigation bar while keeping its background behind it.
 * `consumeWindowInsets` then tells the tab's own Scaffold that the bottom is
 * already spoken for, so it applies only the top.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TabScaffold(navController: NavHostController, content: @Composable () -> Unit) {
    val backStackEntry: NavBackStackEntry? by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route ?: Destinations.CHATS

    Scaffold(
        containerColor = LlmTheme.colors.app,
        contentWindowInsets = WindowInsets(0),
        bottomBar = {
            AppBottomBar(currentRoute = currentRoute) { route ->
                if (route != currentRoute) {
                    navController.navigate(route) {
                        popUpTo(Destinations.CHATS) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            }
        },
    ) { padding ->
        Box(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .consumeWindowInsets(padding),
        ) { content() }
    }
}

private fun NavHostController.toConnect() {
    if (currentDestination?.route == Destinations.CONNECT) return
    navigate(Destinations.CONNECT) {
        popUpTo(graph.id) { inclusive = true }
        launchSingleTop = true
    }
}
