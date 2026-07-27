/**
 * Native bindings for the encrypted session storage ports.
 *
 * Deliberately thin: this file only maps Expo SecureStore, Expo Crypto, and
 * AsyncStorage onto the ports declared in `secure-session-storage.ts`. All
 * envelope, versioning, and failure logic lives there so it can be tested
 * without a device.
 *
 * Expo SDK 56's `expo-crypto` provides real authenticated AES-GCM
 * (`aesEncryptAsync`/`aesDecryptAsync`, with nonce, tag length, and additional
 * authenticated data), so no third-party AES library is used and no unauthenticated
 * mode such as AES-CTR appears anywhere in this app.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  AESEncryptionKey,
  AESKeySize,
  AESSealedData,
  aesDecryptAsync,
  aesEncryptAsync,
} from "expo-crypto";
import * as SecureStore from "expo-secure-store";

import type {
  CiphertextStore,
  SessionCrypto,
  SessionKeyStore,
} from "./secure-session-storage";

/** 96-bit nonce and 128-bit tag: the values AES-GCM is specified around. */
const NONCE_BYTE_LENGTH = 12;
const TAG_BYTE_LENGTH = 16;

/**
 * One stable service for read, write, and delete.
 *
 * On iOS this is `kSecAttrService`; on Android it is the key alias. It must be
 * identical across all three operations or a written entry becomes unreadable.
 *
 * `WHEN_UNLOCKED_THIS_DEVICE_ONLY` keeps the key off backups and off any
 * restored device. `requireAuthentication` is deliberately absent: biometric
 * prompts are out of scope, and enabling it would also require a Face ID usage
 * description this app does not declare.
 */
const SECURE_STORE_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainService: "com.runperformance.session",
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

function utf8Bytes(value: string): Uint8Array {
  return new TextEncoder().encode(value);
}

function utf8String(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes);
}

export const nativeSessionKeyStore: SessionKeyStore = {
  read(keyName) {
    return SecureStore.getItemAsync(keyName, SECURE_STORE_OPTIONS);
  },
  write(keyName, keyMaterial) {
    return SecureStore.setItemAsync(keyName, keyMaterial, SECURE_STORE_OPTIONS);
  },
  remove(keyName) {
    return SecureStore.deleteItemAsync(keyName, SECURE_STORE_OPTIONS);
  },
};

export const nativeCiphertextStore: CiphertextStore = {
  read(storageKey) {
    return AsyncStorage.getItem(storageKey);
  },
  write(storageKey, envelope) {
    return AsyncStorage.setItem(storageKey, envelope);
  },
  remove(storageKey) {
    return AsyncStorage.removeItem(storageKey);
  },
};

export const nativeSessionCrypto: SessionCrypto = {
  async generateKey() {
    const key = await AESEncryptionKey.generate(AESKeySize.AES256);

    return key.encoded("base64");
  },

  async seal({ keyMaterial, plaintext, additionalData }) {
    const key = await AESEncryptionKey.import(keyMaterial, "base64");
    const sealed = await aesEncryptAsync(utf8Bytes(plaintext), key, {
      // A fresh nonce per call, generated natively. Reusing one under the same
      // key would break GCM outright.
      nonce: { length: NONCE_BYTE_LENGTH },
      tagLength: TAG_BYTE_LENGTH,
      additionalData: utf8Bytes(additionalData),
    });

    return sealed.combined("base64");
  },

  async open({ keyMaterial, sealed, additionalData }) {
    const key = await AESEncryptionKey.import(keyMaterial, "base64");
    // Throws on a malformed payload, and `aesDecryptAsync` throws on a failed
    // tag. Both are caught by the adapter and become "no session".
    const data = AESSealedData.fromCombined(sealed, {
      ivLength: NONCE_BYTE_LENGTH,
      tagLength: TAG_BYTE_LENGTH,
    });
    const plaintext = await aesDecryptAsync(data, key, {
      output: "bytes",
      additionalData: utf8Bytes(additionalData),
    });

    return utf8String(plaintext);
  },
};
