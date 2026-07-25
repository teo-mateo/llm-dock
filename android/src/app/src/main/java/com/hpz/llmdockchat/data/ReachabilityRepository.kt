package com.hpz.llmdockchat.data

import com.hpz.llmdockchat.core.error.AppError
import com.hpz.llmdockchat.core.net.appError

/**
 * What `GET /api/health` says about an address the user typed (F01-R2).
 *
 * The distinction is the whole point: "wrong host" and "wrong code" are the two
 * failures a user cannot otherwise tell apart, because both surface as a login
 * that does not work.
 */
sealed interface Reachability {
    data object Dashboard : Reachability
    data object NotADashboard : Reachability
    data class Unreachable(val detail: String) : Reachability
}

class ReachabilityRepository(private val health: HealthRepository) {

    suspend fun probe(): Reachability = health.health().fold(
        onSuccess = { server ->
            if (server.healthy) Reachability.Dashboard else Reachability.NotADashboard
        },
        onFailure = { failure ->
            when (val error = failure.appError) {
                // The bare cause ("Failed to connect to /10.0.2.99:3399"), not
                // its display form: the caller supplies its own lead-in and
                // would otherwise say "could not reach" twice.
                is AppError.Network ->
                    Reachability.Unreachable(error.cause.message?.takeIf { it.isNotBlank() }.orEmpty())
                // Something is listening and it is not the dashboard: a proxy,
                // a model server (`api.ai.heapzilla.eu` answers /api/health with
                // an OpenAI-shaped error), or a wrong port.
                else -> Reachability.NotADashboard
            }
        },
    )
}
