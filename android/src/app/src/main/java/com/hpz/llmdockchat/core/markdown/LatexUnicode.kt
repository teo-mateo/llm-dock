package com.hpz.llmdockchat.core.markdown

/**
 * Turns the small, common subset of inline LaTeX that chat models actually emit
 * into plain Unicode.
 *
 * This is not a maths renderer and does not try to be one — F05 dropped LaTeX
 * rendering, and that stands for anything with real structure (fractions,
 * matrices, integrals with limits). But "dropped" was being read as "print the
 * source", so a sentence like
 *
 * ```
 * Time (low pay) $\rightarrow$ Reliability (medium pay)
 * ```
 *
 * reached the screen with `$\rightarrow$` in it, twice, in monospace. An arrow
 * between two words is not maths worth a renderer; it is a word the model spelt
 * in TeX. Substituting the symbol costs a lookup table and fixes the overwhelming
 * majority of what shows up mid-sentence.
 *
 * [translate] returns null when the span still contains LaTeX it cannot
 * faithfully represent — the caller then falls back to showing the source, which
 * is honest, rather than a mangled half-translation that silently drops terms.
 */
object LatexUnicode {

    fun translate(source: String): String? {
        var text = source.trim()
        if (text.isEmpty()) return null

        // `\text{…}`, `\mathrm{…}` and friends are pure wrappers: the content is
        // ordinary prose that only needed escaping to sit inside maths.
        text = WRAPPER_RE.replace(text) { it.groupValues[2] }

        for ((command, symbol) in SYMBOLS) {
            // Word-boundary on the tail so \int does not eat the \intercal case,
            // and so \alpha is not matched inside \alphabeta.
            text = text.replace(Regex(Regex.escape(command) + "(?![a-zA-Z])"), symbol)
        }

        text = SUPERSCRIPT_RE.replace(text) { m ->
            m.groupValues[1].map { SUPERSCRIPTS[it] ?: return@replace m.value }.joinToString("")
        }
        text = SUBSCRIPT_RE.replace(text) { m ->
            m.groupValues[1].map { SUBSCRIPTS[it] ?: return@replace m.value }.joinToString("")
        }

        text = text.replace("\\,", "\u2009").replace("\\;", " ").replace("\\ ", " ")
        text = text.replace("\\{", "{").replace("\\}", "}").replace("\\%", "%")

        // Anything left holding a command, a brace group or an alignment marker
        // is beyond this table. Say so rather than guess.
        if (text.contains('\\') || text.contains('{') || text.contains('}') || text.contains('&')) {
            return null
        }
        return text.replace(Regex("\\s+"), " ").trim().takeIf { it.isNotEmpty() }
    }

    private val WRAPPER_RE = Regex("""\\(text|mathrm|mathbf|mathit|operatorname)\{([^{}]*)\}""")
    private val SUPERSCRIPT_RE = Regex("""\^\{?([0-9n+\-i]+)\}?""")
    private val SUBSCRIPT_RE = Regex("""_\{?([0-9aeoxjhklmnpstiru+\-]+)\}?""")

    private val SUPERSCRIPTS = mapOf(
        '0' to '⁰', '1' to '¹', '2' to '²', '3' to '³', '4' to '⁴',
        '5' to '⁵', '6' to '⁶', '7' to '⁷', '8' to '⁸', '9' to '⁹',
        'n' to 'ⁿ', 'i' to 'ⁱ', '+' to '⁺', '-' to '⁻',
    )

    private val SUBSCRIPTS = mapOf(
        '0' to '₀', '1' to '₁', '2' to '₂', '3' to '₃', '4' to '₄',
        '5' to '₅', '6' to '₆', '7' to '₇', '8' to '₈', '9' to '₉',
        'a' to 'ₐ', 'e' to 'ₑ', 'o' to 'ₒ', 'x' to 'ₓ', 'h' to 'ₕ',
        'k' to 'ₖ', 'l' to 'ₗ', 'm' to 'ₘ', 'n' to 'ₙ', 'p' to 'ₚ',
        's' to 'ₛ', 't' to 'ₜ', 'i' to 'ᵢ', 'r' to 'ᵣ', 'u' to 'ᵤ',
        'j' to 'ⱼ', '+' to '₊', '-' to '₋',
    )

    /** Longest first, so `\leftrightarrow` is not consumed by `\leftarrow`. */
    private val SYMBOLS: List<Pair<String, String>> = listOf(
        "\\leftrightarrow" to "↔", "\\Leftrightarrow" to "⇔",
        "\\rightarrow" to "→", "\\Rightarrow" to "⇒",
        "\\leftarrow" to "←", "\\Leftarrow" to "⇐",
        "\\longrightarrow" to "⟶", "\\longleftarrow" to "⟵",
        "\\uparrow" to "↑", "\\downarrow" to "↓",
        "\\mapsto" to "↦", "\\to" to "→", "\\gets" to "←",
        "\\times" to "×", "\\div" to "÷", "\\cdot" to "·", "\\ast" to "∗",
        "\\pm" to "±", "\\mp" to "∓",
        "\\leq" to "≤", "\\le" to "≤", "\\geq" to "≥", "\\ge" to "≥",
        "\\neq" to "≠", "\\ne" to "≠", "\\approx" to "≈", "\\equiv" to "≡",
        "\\sim" to "∼", "\\propto" to "∝", "\\ll" to "≪", "\\gg" to "≫",
        "\\infty" to "∞", "\\partial" to "∂", "\\nabla" to "∇",
        "\\sum" to "∑", "\\prod" to "∏", "\\int" to "∫", "\\sqrt" to "√",
        "\\forall" to "∀", "\\exists" to "∃", "\\in" to "∈", "\\notin" to "∉",
        "\\subset" to "⊂", "\\subseteq" to "⊆", "\\cup" to "∪", "\\cap" to "∩",
        "\\emptyset" to "∅", "\\varnothing" to "∅",
        "\\land" to "∧", "\\lor" to "∨", "\\neg" to "¬",
        "\\deg" to "°", "\\circ" to "∘", "\\bullet" to "•",
        "\\ldots" to "…", "\\dots" to "…", "\\cdots" to "⋯",
        "\\alpha" to "α", "\\beta" to "β", "\\gamma" to "γ", "\\delta" to "δ",
        "\\epsilon" to "ε", "\\varepsilon" to "ε", "\\zeta" to "ζ", "\\eta" to "η",
        "\\theta" to "θ", "\\iota" to "ι", "\\kappa" to "κ", "\\lambda" to "λ",
        "\\mu" to "μ", "\\nu" to "ν", "\\xi" to "ξ", "\\pi" to "π",
        "\\rho" to "ρ", "\\sigma" to "σ", "\\tau" to "τ", "\\upsilon" to "υ",
        "\\phi" to "φ", "\\varphi" to "φ", "\\chi" to "χ", "\\psi" to "ψ",
        "\\omega" to "ω",
        "\\Gamma" to "Γ", "\\Delta" to "Δ", "\\Theta" to "Θ", "\\Lambda" to "Λ",
        "\\Xi" to "Ξ", "\\Pi" to "Π", "\\Sigma" to "Σ", "\\Phi" to "Φ",
        "\\Psi" to "Ψ", "\\Omega" to "Ω",
    )
}
