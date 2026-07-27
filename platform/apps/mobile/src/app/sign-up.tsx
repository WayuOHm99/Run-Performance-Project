import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { Notice } from "@/components/notice";
import { PrimaryButton } from "@/components/primary-button";
import { ScreenHeading } from "@/components/screen-heading";
import { TextField } from "@/components/text-field";
import { useAuth } from "@/features/auth/auth-provider";
import { signUpWithPassword } from "@/features/auth/auth-repository";
import {
  credentialMessage,
  validateCredentials,
  type CredentialField,
} from "@/features/auth/credentials";
import { authErrorMessage } from "@/features/auth/errors";
import {
  beginSubmission,
  endSubmission,
  isSubmitting,
  type SubmissionState,
} from "@/features/auth/submission";
import { spacing } from "@/theme/tokens";

export default function SignUpScreen() {
  const { client, beginEmailConfirmation } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldError, setFieldError] = useState<CredentialField | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submission, setSubmission] = useState<SubmissionState>("idle");

  const submit = () => {
    const attempt = beginSubmission(submission);

    // Dropping the second tap matters more here than on sign-in: a duplicate
    // signUp burns the email rate limit and can send two confirmation mails.
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
        const outcome = await signUpWithPassword(client, validated.value);

        if (outcome.kind === "confirmation-required") {
          // No session came back, so the project requires confirmation. The
          // gate moves to the check-email state; there is no deep-link handler
          // in this task, so the user returns and signs in manually.
          beginEmailConfirmation();
          return;
        }

        // A session came back: the auth state change redirects from here.
      } catch (error) {
        setMessage(authErrorMessage(error));
      } finally {
        setPassword("");
        setSubmission(endSubmission());
      }
    })();
  };

  const busy = isSubmitting(submission);

  return (
    <AppScreen>
      <ScreenHeading
        title="สร้างบัญชี"
        description="ใช้อีเมลและรหัสผ่านเท่านั้น บทบาทและทีมจะถูกกำหนดโดยโค้ชในภายหลัง"
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
          autoComplete="new-password"
          editable={!busy}
          error={fieldError === "password" ? (message ?? undefined) : undefined}
        />

        {message !== null && fieldError === null ? (
          <Notice title="สร้างบัญชีไม่สำเร็จ" message={message} />
        ) : null}

        <PrimaryButton label="สร้างบัญชี" onPress={submit} busy={busy} />
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
