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
import {
  useAccountQuery,
  useSaveDisplayName,
} from "@/features/profile/use-account";
import { spacing } from "@/theme/tokens";

/**
 * Authenticated profile editing and global sign-out.
 *
 * Reachable by a user with an active membership and by one without, because a
 * revoked user keeps exactly this capability: they may still correct their own
 * name even though no role area is open to them.
 */
export default function ProfileScreen() {
  const { signOut } = useAuth();
  const account = useAccountQuery();
  const saveDisplayName = useSaveDisplayName();

  const [draft, setDraft] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [submission, setSubmission] = useState<SubmissionState>("idle");

  // Falls back to the loaded value until the user edits, so the field shows the
  // stored name without an effect that could clobber an in-progress edit.
  const value = draft ?? account.data?.displayName ?? "";

  const submit = () => {
    const attempt = beginSubmission(submission);

    if (!attempt.accepted) {
      return;
    }

    const validated = validateDisplayName(value);

    if (!validated.ok) {
      setSaved(false);
      setMessage(displayNameMessage(validated.reason));
      return;
    }

    setMessage(null);
    setSaved(false);
    setSubmission(attempt.next);

    void (async () => {
      try {
        await saveDisplayName.mutateAsync(validated.value);
        setDraft(null);
        setSaved(true);
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
        title="บัญชีของฉัน"
        description="แก้ไขชื่อที่ใช้แสดง หรือออกจากระบบทุกอุปกรณ์"
      />

      <View style={styles.form}>
        <TextField
          label="ชื่อที่ใช้แสดง"
          value={value}
          onChangeText={setDraft}
          autoComplete="name"
          editable={!busy && !account.isLoading}
          maxLength={DISPLAY_NAME_MAX_LENGTH}
        />

        {message === null ? null : (
          <Notice title="บันทึกไม่สำเร็จ" message={message} />
        )}
        {saved ? (
          <Notice title="บันทึกแล้ว" message="อัปเดตชื่อที่ใช้แสดงเรียบร้อย" />
        ) : null}

        <PrimaryButton label="บันทึก" onPress={submit} busy={busy} />
        <PrimaryButton
          label="ออกจากระบบทุกอุปกรณ์"
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
