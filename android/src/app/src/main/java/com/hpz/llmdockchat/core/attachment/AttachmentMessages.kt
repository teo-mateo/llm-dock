package com.hpz.llmdockchat.core.attachment

/**
 * What a caller says when an attachment cannot be read. Owned here because both
 * the share intake and the composer's attach/camera flows produce them, and a
 * message about a photo is not share policy.
 */
const val IMAGE_UNREADABLE = "That image could not be read."
const val PHOTO_UNREADABLE = "That photo could not be read."
const val FILE_UNREADABLE = "That file could not be read."
