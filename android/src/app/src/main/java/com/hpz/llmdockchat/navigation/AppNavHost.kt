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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavController
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
import com.hpz.llmdockchat.feature.designlab.DesignLabGalleryScreen
import com.hpz.llmdockchat.feature.account.AccountScreen
import com.hpz.llmdockchat.feature.account.AccountViewModel
import com.hpz.llmdockchat.feature.connect.ConnectScreen
import com.hpz.llmdockchat.feature.connect.ConnectViewModel
import com.hpz.llmdockchat.feature.conversations.ConversationListScreen
import com.hpz.llmdockchat.feature.conversations.ConversationListViewModel
import com.hpz.llmdockchat.feature.logs.LogsViewModel
import com.hpz.llmdockchat.feature.models.ModelDetailScreen
import com.hpz.llmdockchat.feature.models.ModelTab
import com.hpz.llmdockchat.feature.models.ModelDetailViewModel
import com.hpz.llmdockchat.feature.models.ModelsScreen
import com.hpz.llmdockchat.feature.models.ModelsViewModel
import com.hpz.llmdockchat.feature.newchat.NewChatScreen
import com.hpz.llmdockchat.feature.newchat.NewChatViewModel
import com.hpz.llmdockchat.feature.share.ShareTargetScreen
import com.hpz.llmdockchat.feature.share.ShareTargetViewModel
import com.hpz.llmdockchat.feature.thread.ThreadScreen
import com.hpz.llmdockchat.feature.thread.ThreadViewModel
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * The app's navigation graph. Connect is a destination like
 * any other rather than a modal in front of the app, so returning to it clears
 * the back stack — a back press from Connect leaves the app instead of walking
 * into a screen the session can no longer load.
 *
 * [Destinations.CHATS] and [Destinations.MODELS] live in the nested
 * [Destinations.TABS] graph and share [AppBottomBar]; [Destinations.THREAD]
 * and [Destinations.NEW_CHAT] are pushed on top of it without one.
 */
@Composable
fun AppNavHost(
    container: AppContainer,
    startDestination: String,
    modifier: Modifier = Modifier,
    navController: NavHostController = rememberNavController(),
) {
    // Raised only when silent re-authentication cannot succeed, and by
    // sign-out. Observed here, once, rather than in every screen —
    // that is the point of observing it once.
    val authenticationRequired by container.sessionState.authenticationRequired.collectAsState()
    LaunchedEffect(authenticationRequired) {
        if (authenticationRequired) navController.toConnect()
    }

    // A staged share navigates to the target picker, wherever the app
    // is: cold start from a share (the store hydrates from disk before the
    // NavHost composes), a share arriving mid-app, or a re-login round trip
    // (Connect's onSignedIn checks the store itself). Skipped while on Connect
    // — the user isn't signed in yet — while already on the picker, so a
    // second share while it's open just replaces the staged content, and while
    // the new-chat sheet is open: the sheet *is* the share flow's
    // continuation screen, and navigating to the picker again while it is open
    // is what puts a second picker on the stack. The route is read inside the
    // effect once the graph has a current destination — during a restore the
    // route is not settled yet at composition — and the push is single-top.
    val pendingShare by container.sharedDraftStore.pending.collectAsState()
    LaunchedEffect(pendingShare) {
        if (pendingShare == null) return@LaunchedEffect
        val route = navController.awaitReadyDestination(SHARE_NAV_READY_TIMEOUT_MS)
            ?: return@LaunchedEffect
        if (route == Destinations.CONNECT ||
            route == Destinations.SHARE_PICKER ||
            route == Destinations.NEW_CHAT ||
            route == Destinations.NEW_CHAT_SUMMARIZE
        ) {
            return@LaunchedEffect
        }
        navController.navigate(Destinations.SHARE_PICKER) { launchSingleTop = true }
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
                    // A share that arrived while signed out resumes on
                    // the target picker after sign-in, not on the Chats tab.
                    val pending = container.sharedDraftStore.pending.value != null
                    navController.navigate(
                        if (pending) Destinations.SHARE_PICKER else Destinations.TABS,
                    ) {
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
                        onOpenAccount = { navController.navigate(Destinations.ACCOUNT) },
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
                        onOpenLogs = { serviceName ->
                            navController.navigate(
                                Destinations.modelDetail(serviceName, Destinations.MODEL_TAB_LOGS),
                            )
                        },
                        onOpenAccount = { navController.navigate(Destinations.ACCOUNT) },
                    )
                }
            }

            composable(Destinations.DESIGN) {
                TabScaffold(navController) { DesignLabGalleryScreen() }
            }
        }

        composable(Destinations.ACCOUNT) {
            val viewModel: AccountViewModel = viewModel(
                factory = viewModelFactory {
                    initializer {
                        AccountViewModel(
                            sessionManager = container.sessionManager,
                            serverUrlStore = container.serverUrlStore,
                        )
                    }
                },
            )
            AccountScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
            )
        }

        composable(
            Destinations.MODEL_DETAIL,
            arguments = listOf(
                navArgument("tab") {
                    type = NavType.StringType
                    defaultValue = Destinations.MODEL_TAB_CONFIG
                },
            ),
        ) { backStackEntry ->
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
            val logsViewModel: LogsViewModel = viewModel(
                key = "logs_$serviceName",
                factory = viewModelFactory {
                    initializer {
                        LogsViewModel(
                            serviceName = serviceName,
                            logsStreamRepository = container.logsStreamRepository,
                            servicesRepository = container.servicesRepository,
                        )
                    }
                },
            )
            ModelDetailScreen(
                viewModel = viewModel,
                logsViewModel = logsViewModel,
                onBack = { navController.popBackStack() },
                initialTab = if (backStackEntry.arguments?.getString("tab") == Destinations.MODEL_TAB_LOGS) {
                    ModelTab.LOGS
                } else {
                    ModelTab.CONFIG
                },
            )
        }

        composable(Destinations.SHARE_PICKER) {
            val pickerScope = rememberCoroutineScope()
            val viewModel: ShareTargetViewModel = viewModel(
                factory = viewModelFactory {
                    initializer {
                        ShareTargetViewModel(
                            repository = container.conversationsRepository,
                            store = container.sharedDraftStore,
                            summarizeLauncher = container.summarizeLauncher,
                        )
                    }
                },
            )
            ShareTargetScreen(
                viewModel = viewModel,
                onPickConversation = { conversation ->
                    // Navigates after the write rather than after the call: the
                    // thread reads the draft and the staged attachments as soon as
                    // it loads, so a merge still in flight would land behind that
                    // read and the thread would open without the shared content.
                    pickerScope.launch {
                        container.sharedDraftStore.reassign(conversation.id, container.draftStore)
                        navController.navigate(Destinations.thread(conversation.id)) {
                            popUpTo(Destinations.SHARE_PICKER) { inclusive = true }
                        }
                    }
                },
                onNewConversation = { navController.navigate(Destinations.newChat()) },
                // The direct path lands on the thread that now owes one
                // turn; a remembered model that is gone or stopped falls back to
                // the sheet, with the share still staged (nothing is lost).
                onSummarize = {
                    viewModel.summarize(
                        onOpened = { conversationId ->
                            navController.navigate(Destinations.thread(conversationId)) {
                                popUpTo(Destinations.SHARE_PICKER) { inclusive = true }
                            }
                        },
                        onChooseModel = { navController.navigate(Destinations.newChatSummarize()) },
                    )
                },
                onDismiss = {
                    container.sharedDraftStore.clearPending()
                    navController.popBackStack()
                },
            )
        }

        composable(Destinations.THREAD) { backStackEntry ->
            val conversationId = backStackEntry.arguments?.getString("conversationId").orEmpty()
            val viewModel: ThreadViewModel = viewModel(
                // Keyed by conversation so two threads visited in a row never
                // share a ViewModel — and so its stream, which is scoped to
                // this destination, dies with the destination.
                key = "thread_$conversationId",
                factory = viewModelFactory {
                    initializer {
                        ThreadViewModel(
                            conversationId = conversationId,
                            repository = container.chatRepository,
                            drafts = container.draftStore,
                            editStates = container.editStateStore,
                            attachmentStore = container.sharedDraftStore,
                            servicesStreamRepository = container.servicesStreamRepository,
                            servicesRepository = container.servicesRepository,
                            openRouterModelsRepository = container.openRouterModelsRepository,
                            conversationsRepository = container.conversationsRepository,
                            mcpServersRepository = container.mcpServersRepository,
                            promptsRepository = container.promptsRepository,
                            attachmentImporter = container.attachmentImporter,
                        )
                    }
                },
            )
            ThreadScreen(viewModel = viewModel, onBack = { navController.popBackStack() })
        }

        composable(
            Destinations.NEW_CHAT,
            arguments = listOf(
                navArgument("service") { type = NavType.StringType; nullable = true; defaultValue = null },
            ),
        ) { backStackEntry ->
            NewChatDestination(
                container = container,
                navController = navController,
                preselectedServiceName = backStackEntry.arguments?.getString("service"),
                summarizeMode = false,
            )
        }

        composable(Destinations.NEW_CHAT_SUMMARIZE) {
            NewChatDestination(
                container = container,
                navController = navController,
                preselectedServiceName = null,
                summarizeMode = true,
            )
        }
    }
}

/**
 * The new-chat sheet, in its two entries (ordinary and summarize). One
 * body so the two cannot drift on what creating a conversation does — the
 * summarize entry differs only in the mode it hands the ViewModel.
 */
@Composable
private fun NewChatDestination(
    container: AppContainer,
    navController: NavHostController,
    preselectedServiceName: String?,
    summarizeMode: Boolean,
) {
    val newChatScope = rememberCoroutineScope()
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
                    summarizeMode = summarizeMode,
                    sharedDraftStore = container.sharedDraftStore,
                )
            }
        },
    )
    NewChatScreen(
        viewModel = viewModel,
        onBack = { navController.popBackStack() },
        onConversationCreated = { id ->
            // A conversation created from the share picker takes
            // the staged content with it; the picker below is popped too
            // so Back from the new thread lands on Chats, not on an
            // empty picker. A summarize run counts as share-origin even
            // though the sheet already spent the pending share filing its
            // claim — the picker is still what sits under this sheet.
            val hadPendingShare = summarizeMode || container.sharedDraftStore.pending.value != null
            // Awaited for the same reason as the picker's pick: the thread must
            // not load before the content it is opening with has been filed. For
            // a summarize run this returns without waiting — the sheet already
            // spent the pending share.
            newChatScope.launch {
                container.sharedDraftStore.reassign(id, container.draftStore)
                // Replaces the sheet on the back stack — Back from the new
                // thread returns to the conversation list, not to a sheet
                // for a chat that already exists.
                navController.navigate(Destinations.thread(id)) {
                    popUpTo(
                        if (hadPendingShare) Destinations.SHARE_PICKER else Destinations.NEW_CHAT,
                    ) { inclusive = true }
                }
            }
        },
    )
}

/**
 * Wraps a tab's content in the shared bottom bar. Tab switches
 * `popUpTo` [Destinations.CHATS] — the [Destinations.TABS] graph's own,
 * fixed start route, not the outer [NavHost]'s (which may be Connect) — with
 * `saveState`/`restoreState`, the standard bottom-nav idiom: each tab's
 * ViewModel and `rememberSaveable` state (including scroll position) survive
 * switching away and back.
 *
 * Insets: this Scaffold applies none of its own
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

/**
 * Zero means the graph never settled. The only way to get there is sitting on
 * Connect with no destination at all, and the sign-in handoff navigates that
 * case itself — so timing out is a safe answer, not a lost share.
 */
private const val SHARE_NAV_READY_TIMEOUT_MS = 1000L

/** The current route once the graph has one, or `null` — during a restore the route is not settled yet at composition. */
private suspend fun NavHostController.awaitReadyDestination(timeoutMs: Long): String? =
    withTimeoutOrNull(timeoutMs) {
        callbackFlow {
            trySend(currentDestination?.route)
            val listener = NavController.OnDestinationChangedListener { _, destination, _ ->
                trySend(destination.route)
            }
            addOnDestinationChangedListener(listener)
            awaitClose { removeOnDestinationChangedListener(listener) }
        }.firstOrNull { it != null }
    }
