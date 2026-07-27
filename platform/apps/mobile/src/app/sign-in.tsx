import { useRouter } from "expo-router";
import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { Notice } from "@/components/notice";
import { PrimaryButton } from "@/components/primary-button";
import { ScreenHeading } from "@/components/screen-heading";
import { TextField } from "@/components/text-field";
import { useAuth } from "@/features/auth/auth-provider";
import { signInWithPassword } from "@/features/auth/auth-repository";
import {
  credentialMessage,
  validateCredentials,
  type CredentialField,
} from "@/features/auth/credentials";
import { authErrorMessage } from "@/features/auth/errors";
import { ROUTES } from "@/features/auth/gate";
import {
  beginSubmission,
  endSubmission,
  isSubmitting,
  type SubmissionState,
} from "@/features/auth/submission";
import { spacing } from "@/theme/tokens";

export default function SignInScreen() {
  const { client } = useAuth();
  const router = useRouter();

  // Credentials live in component state and nowhere else. Nothing here writes
  // them to storage, a query cache, a log, or an error message.
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldError, setFieldError] = useState<CredentialField | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submission, setSubmission] = useState<SubmissionState>("idle");

  const submit = () => {
    const attempt = beginSubmission(submission);

    // A second tap while the first request is in flight is dropped outright.
    if (!attempt.accepted) {
      return;
    }

    const validated = validateCredentials({ email, password });

    if (!validated.ok) {
      setFieldError(validated.field);
      setMessage(credentialMessage(validated.reason));
      return;
    }

    setFieldError(null);
    setMessage(null);
    setSubmission(attempt.next);

    void (async () => {
      try {
        await signInWithPassword(client, validated.value);
        // The auth state change drives the redirect; nothing to navigate here.
      } catch (error) {
        setMessage(authErrorMessage(error));
      } finally {
        // Cleared on every completed attempt, success or failure, so the value
        // stops being held in state as soon as it has been used.
        setPassword("");
        setSubmission(endSubmission());
      }
    })();
  };

  const busy = isSubmitting(submission);

  return (
    <AppScreen>
      <ScreenHeading
        eyebrow="RUN PERFORMANCE"
        title="เข้าสู่ระบบ"
        description="ใช้อีเมลและรหัสผ่านของคุณเพื่อเข้าใช้งาน"
      />

      <View style={styles.form}>
        <TextField
          label="อีเมล"
          value={email}
          onChangeText={setEmail}
          placeholder="you@example.com"
          autoComplete="email"
          keyboardType="email-address"
          editable={!busy}
          error={fieldError === "email" ? (message ?? undefined) : undefined}
        />
        <TextField
          label="รหัสผ่าน"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="password"
          editable={!busy}
          error={fieldError === "password" ? (message ?? undefined) : undefined}
        />

        {message !== null && fieldError === null ? (
          <Notice title="เข้าสู่ระบบไม่สำเร็จ" message={message} />
        ) : null}

        <PrimaryButton label="เข้าสู่ระบบ" onPress={submit} busy={busy} />
        <PrimaryButton
          label="ยังไม่มีบัญชี? สร้างบัญชีใหม่"
          variant="quiet"
          disabled={busy}
          onPress={() => {
            router.push(ROUTES.signUp);
          }}
        />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  form: {
    gap: spacing.lg,
    marginTop: spacing.lg,
  },
});
