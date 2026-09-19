package com.hpz.llmdockchat.data.mapper

import com.hpz.llmdockchat.data.dto.UrlFetchDto
import com.hpz.llmdockchat.data.dto.UrlFetchFailureDto
import com.hpz.llmdockchat.data.dto.UrlFetchServerDto
import com.hpz.llmdockchat.data.model.UrlFetchFailure
import com.hpz.llmdockchat.data.model.UrlFetchServer
import com.hpz.llmdockchat.data.model.UrlRetrieval

fun UrlFetchDto.toDomain(): UrlRetrieval = UrlRetrieval(
    supported = true,
    servers = servers.map { it.toDomain() },
    failures = failures.map { it.toDomain() },
)

fun UrlFetchServerDto.toDomain(): UrlFetchServer = UrlFetchServer(id = id, name = name, tools = tools)

fun UrlFetchFailureDto.toDomain(): UrlFetchFailure = UrlFetchFailure(id = id, error = error)
