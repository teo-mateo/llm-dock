package com.hpz.llmdockchat.feature.connect

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.hpz.llmdockchat.core.ui.theme.LLMDockChatTheme
import com.hpz.llmdockchat.core.ui.theme.LlmTheme

/**
 * Screen 01 · Connect. Both ways in are on the one screen, as the dashboard's
 * own login page has them (F01-R4): no menu, no second screen.
 */
@Composable
fun ConnectScreen(viewModel: ConnectViewModel, onSignedIn: () -> Unit, modifier: Modifier = Modifier) {
    val state by viewModel.state.collectAsState()

    LaunchedEffect(state.signedIn) {
        if (state.signedIn) onSignedIn()
    }

    ConnectContent(
        state = state,
        onAddressChange = viewModel::onAddressChange,
        onMethodChange = viewModel::onMethodChange,
        onPasswordChange = viewModel::onPasswordChange,
        onPasswordVisibilityToggle = viewModel::onPasswordVisibilityToggle,
        onCodeChange = viewModel::onCodeChange,
        onSubmit = viewModel::submit,
        modifier = modifier,
    )
}

@Composable
private fun ConnectContent(
    state: ConnectUiState,
    onAddressChange: (String) -> Unit,
    onMethodChange: (LoginMethod) -> Unit,
    onPasswordChange: (String) -> Unit,
    onPasswordVisibilityToggle: () -> Unit,
    onCodeChange: (String) -> Unit,
    onSubmit: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val colors = LlmTheme.colors
    val keyboard = LocalSoftwareKeyboardController.current

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(colors.app)
            // Connect has no Scaffold, so it owns its own insets (fix pass
            // A2 — nothing above it supplies any). `safeDrawing` is the union
            // of the system bars, the cutout and the IME, and it sits
            // *outside* the scroll so the keyboard shrinks the viewport and
            // the form scrolls inside it. Inside the scroll — where
            // `imePadding()` used to be — it only lengthened the content,
            // which on a window the OEM also resizes for the IME meant the
            // keyboard was paid for twice (fix pass B1).
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 22.dp, vertical = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Mark()
        Spacer(Modifier.height(14.dp))
        Text(
            "llm-dock",
            style = MaterialTheme.typography.titleLarge,
            color = colors.fg,
        )
        Text(
            "Connect to your rig",
            style = MaterialTheme.typography.bodyMedium,
            color = colors.muted,
            modifier = Modifier.padding(top = 5.dp),
        )

        Spacer(Modifier.height(30.dp))

        OutlinedTextField(
            value = state.address,
            onValueChange = onAddressChange,
            label = { Text("Server") },
            placeholder = { Text("http://10.0.2.2:3399") },
            singleLine = true,
            isError = state.addressError != null,
            supportingText = state.addressError?.let { { Text(it, color = colors.red) } },
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Uri,
                autoCorrectEnabled = false,
                capitalization = KeyboardCapitalization.None,
                imeAction = ImeAction.Next,
            ),
            colors = fieldColors(),
            modifier = Modifier
                .fillMaxWidth()
                .testTag("connect_server"),
        )

        Spacer(Modifier.height(18.dp))

        MethodSelector(state.method, onMethodChange)

        Spacer(Modifier.height(18.dp))

        when (state.method) {
            LoginMethod.PASSWORD -> PasswordField(
                state = state,
                onPasswordChange = onPasswordChange,
                onVisibilityToggle = onPasswordVisibilityToggle,
                onSubmit = {
                    keyboard?.hide()
                    onSubmit()
                },
            )
            LoginMethod.CODE -> CodeField(state = state, onCodeChange = onCodeChange)
        }

        state.failure?.let { Banner(it, colors.red) }
        state.notice?.takeIf { state.failure == null }?.let { Banner(it, colors.amber) }

        Spacer(Modifier.height(22.dp))

        Button(
            onClick = {
                keyboard?.hide()
                onSubmit()
            },
            enabled = state.canSubmit,
            colors = ButtonDefaults.buttonColors(
                containerColor = colors.accent,
                contentColor = colors.onAccent,
                disabledContainerColor = colors.surfaceElevated,
                disabledContentColor = colors.subtle,
            ),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier
                .fillMaxWidth()
                .height(50.dp)
                .testTag("connect_submit"),
        ) {
            if (state.busy) {
                CircularProgressIndicator(
                    strokeWidth = 2.dp,
                    color = colors.onAccent,
                    modifier = Modifier.size(18.dp),
                )
                Spacer(Modifier.width(10.dp))
            }
            Text(if (state.busy) "Connecting…" else "Connect")
        }

        Spacer(Modifier.height(18.dp))

        Text(
            text = when (state.method) {
                LoginMethod.PASSWORD ->
                    "The password is the dashboard's DASHBOARD_TOKEN. It is kept " +
                        "encrypted on this device so the session renews itself and you " +
                        "stay signed in until you sign out."
                LoginMethod.CODE ->
                    "An authenticator code cannot be saved, so when this session ends " +
                        "you will be asked for a new one. Sign in with the password " +
                        "instead to stay signed in indefinitely."
            },
            style = MaterialTheme.typography.labelMedium,
            color = colors.subtle,
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
private fun Mark() {
    val colors = LlmTheme.colors
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .size(56.dp)
            .background(colors.surface, RoundedCornerShape(16.dp))
            .border(1.dp, colors.line, RoundedCornerShape(16.dp)),
    ) {
        Text("▮▯", color = colors.accent, fontSize = 20.sp)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MethodSelector(method: LoginMethod, onMethodChange: (LoginMethod) -> Unit) {
    val colors = LlmTheme.colors
    val options = listOf(LoginMethod.PASSWORD to "Password", LoginMethod.CODE to "Auth code")
    SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
        options.forEachIndexed { index, (value, label) ->
            SegmentedButton(
                selected = method == value,
                onClick = { onMethodChange(value) },
                shape = SegmentedButtonDefaults.itemShape(index, options.size),
                colors = SegmentedButtonDefaults.colors(
                    activeContainerColor = colors.accentDeep,
                    activeContentColor = colors.onAccent,
                    activeBorderColor = colors.accent,
                    inactiveContainerColor = colors.surface,
                    inactiveContentColor = colors.muted,
                    inactiveBorderColor = colors.line,
                ),
                modifier = Modifier.testTag("connect_method_${value.name.lowercase()}"),
            ) {
                Text(label)
            }
        }
    }
}

@Composable
private fun PasswordField(
    state: ConnectUiState,
    onPasswordChange: (String) -> Unit,
    onVisibilityToggle: () -> Unit,
    onSubmit: () -> Unit,
) {
    OutlinedTextField(
        value = state.password,
        onValueChange = onPasswordChange,
        label = { Text("Password") },
        singleLine = true,
        visualTransformation = if (state.passwordVisible) {
            VisualTransformation.None
        } else {
            PasswordVisualTransformation()
        },
        keyboardOptions = KeyboardOptions(
            keyboardType = KeyboardType.Password,
            autoCorrectEnabled = false,
            imeAction = ImeAction.Go,
        ),
        keyboardActions = KeyboardActions(onGo = { onSubmit() }),
        trailingIcon = {
            TextButton(
                onClick = onVisibilityToggle,
                modifier = Modifier.testTag("connect_password_reveal"),
            ) {
                Text(
                    if (state.passwordVisible) "Hide" else "Show",
                    style = MaterialTheme.typography.labelMedium,
                    color = LlmTheme.colors.accent,
                )
            }
        },
        colors = fieldColors(),
        modifier = Modifier
            .fillMaxWidth()
            .testTag("connect_password"),
    )
}

/**
 * Six cells over one hidden field: a numeric keyboard, no separate submit, and
 * the caret visible where the next digit lands (F01-R3).
 */
@Composable
private fun CodeField(state: ConnectUiState, onCodeChange: (String) -> Unit) {
    val colors = LlmTheme.colors
    val focusRequester = remember { FocusRequester() }

    LaunchedEffect(Unit) { focusRequester.requestFocus() }

    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
        Text(
            "AUTHENTICATOR CODE",
            style = MaterialTheme.typography.labelSmall,
            color = colors.subtle,
            fontFamily = FontFamily.Monospace,
        )
        Spacer(Modifier.height(12.dp))
        BasicTextField(
            value = state.code,
            onValueChange = onCodeChange,
            enabled = !state.busy,
            singleLine = true,
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.NumberPassword,
                imeAction = ImeAction.Done,
            ),
            textStyle = TextStyle(color = androidx.compose.ui.graphics.Color.Transparent),
            cursorBrush = androidx.compose.ui.graphics.SolidColor(
                androidx.compose.ui.graphics.Color.Transparent,
            ),
            decorationBox = {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(9.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    repeat(CODE_LENGTH) { index ->
                        val filled = index < state.code.length
                        val active = index == state.code.length
                        Box(
                            contentAlignment = Alignment.Center,
                            modifier = Modifier
                                .weight(1f)
                                .height(54.dp)
                                .background(colors.surface, RoundedCornerShape(10.dp))
                                .border(
                                    width = if (active) 2.dp else 1.dp,
                                    color = if (active) colors.accent else colors.line,
                                    shape = RoundedCornerShape(10.dp),
                                ),
                        ) {
                            Text(
                                text = if (filled) state.code[index].toString() else "",
                                color = colors.fg,
                                fontSize = 22.sp,
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                    }
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .focusRequester(focusRequester)
                .testTag("connect_code"),
        )
    }
}

@Composable
private fun Banner(message: String, accent: androidx.compose.ui.graphics.Color) {
    val colors = LlmTheme.colors
    Box(
        modifier = Modifier
            .padding(top = 16.dp)
            .fillMaxWidth()
            .background(colors.surface, RoundedCornerShape(10.dp))
            .border(1.dp, accent.copy(alpha = 0.45f), RoundedCornerShape(10.dp))
            .padding(horizontal = 14.dp, vertical = 11.dp),
    ) {
        Text(
            message,
            style = MaterialTheme.typography.bodyMedium,
            color = accent,
            modifier = Modifier.testTag("connect_message"),
        )
    }
}

@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedTextColor = LlmTheme.colors.fg,
    unfocusedTextColor = LlmTheme.colors.fg,
    focusedContainerColor = LlmTheme.colors.surface,
    unfocusedContainerColor = LlmTheme.colors.surface,
    errorContainerColor = LlmTheme.colors.surface,
    focusedBorderColor = LlmTheme.colors.accent,
    unfocusedBorderColor = LlmTheme.colors.line,
    errorBorderColor = LlmTheme.colors.red,
    focusedLabelColor = LlmTheme.colors.accent,
    unfocusedLabelColor = LlmTheme.colors.subtle,
    cursorColor = LlmTheme.colors.accent,
    focusedPlaceholderColor = LlmTheme.colors.subtle,
    unfocusedPlaceholderColor = LlmTheme.colors.subtle,
)

@Preview
@Composable
private fun ConnectPasswordDarkPreview() {
    LLMDockChatTheme(darkTheme = true) {
        ConnectContent(
            state = ConnectUiState(address = "http://10.0.2.2:3399", password = "secret"),
            onAddressChange = {}, onMethodChange = {}, onPasswordChange = {},
            onPasswordVisibilityToggle = {}, onCodeChange = {}, onSubmit = {},
        )
    }
}

@Preview
@Composable
private fun ConnectCodeLightPreview() {
    LLMDockChatTheme(darkTheme = false) {
        ConnectContent(
            state = ConnectUiState(
                address = "https://dock.example",
                method = LoginMethod.CODE,
                code = "419",
                failure = "Invalid TOTP code",
            ),
            onAddressChange = {}, onMethodChange = {}, onPasswordChange = {},
            onPasswordVisibilityToggle = {}, onCodeChange = {}, onSubmit = {},
        )
    }
}
