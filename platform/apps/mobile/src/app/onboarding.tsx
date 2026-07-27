import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { Notice } from "@/components/notice";
import { PrimaryButton } from "@/components/primary-button";
import { ScreenHeading } from "@/components/screen-heading";
import { TextField } from "@/components/text-field";
import { useAuth } from "@/features/auth/auth-provider";
import {
  DISPLAY_NAME_MAX_LENGTH,
  displayNameMessage,
  validateDisplayName,
} from "@/features/auth/display-name";
import { dataErrorMessage } from "@/features/auth/errors";
import {
  beginSubmission,
  endSubmission,
  isSubmitting,
  type SubmissionState,
} from "@/features/auth/submission";
import { useSaveDisplayName } from "@/features/profile/use-account";
import { spacing } from "@/theme/tokens";

/**
 * Profile onboarding.
 *
 * Blocks role routing until a valid display name exists. The gate is what
 * enforces that -- this screen only supplies the name -- so there is no way to
 * skip past it by navigating directly.
 */
export default function OnboardingScreen() {
  const { signOut } = useAuth();
  const saveDisplayName = useSaveDisplayName();

  const [displayName, setDisplayName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [submission, setSubmission] = useState<SubmissionState>("idle");

  const submit = () => {
    const attempt = beginSubmission(submission);

    if (!attempt.accepted) {
      return;
    }

    const validated = validateDisplayName(displayName);

    if (!validated.ok) {
      setMessage(displayNameMessage(validated.reason));
      return;
    }

    setMessage(null);
    setSubmission(attempt.next);

    void (async () => {
      try {
        await saveDisplayName.mutateAsync(validated.value);
        // The refreshed account moves the gate past onboarding on its own.
      } catch (error) {
        setMessage(dataErrorMessage(error));
      } finally {
        setSubmission(endSubmission());
      }
    })();
  };

  const busy = isSubmitting(submission);

  return (
    <AppScreen>
      <ScreenHeading
        eyebrow="ขั้นตอนสุดท้าย"
        title="ตั้งชื่อที่ใช้แสดง"
        description="ชื่อนี้จะแสดงให้โค้ชในทีมของคุณเห็น และแก้ไขภายหลังได้"
      />

      <View style={styles.form}>
        <TextField
          label="ชื่อที่ใช้แสดง"
          value={displayName}
          onChangeText={setDisplayName}
          placeholder="เช่น ชื่อเล่นของคุณ"
          autoComplete="name"
          editable={!busy}
          maxLength={DISPLAY_NAME_MAX_LENGTH}
        />

        {message === null ? null : (
          <Notice title="บันทึกไม่สำเร็จ" message={message} />
        )}

        <PrimaryButton label="บันทึกและไปต่อ" onPress={submit} busy={busy} />
        <PrimaryButton
          label="ออกจากระบบ"
          variant="quiet"
          disabled={busy}
          onPress={() => {
            void signOut();
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
