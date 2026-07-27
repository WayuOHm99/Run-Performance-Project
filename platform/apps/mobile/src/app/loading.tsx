import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { Notice } from "@/components/notice";
import { PrimaryButton } from "@/components/primary-button";
import { useAuth } from "@/features/auth/auth-provider";
import { useAuthGate, useRetryAccount } from "@/features/profile/use-account";
import { colors, spacing, type } from "@/theme/tokens";

/**
 * The neutral state shown while the session is being restored and while the
 * account is loading, plus the recoverable error state.
 *
 * Restoration and loading deliberately render the same neutral view, so nothing
 * about whether a session exists leaks before the gate has decided. A failure
 * shows a retry here rather than falling through to the pending screen: an
 * error and "no active team" are different answers and must not look alike.
 */
export default function LoadingScreen() {
  const gate = useAuthGate();
  const retry = useRetryAccount();
  const { signOut } = useAuth();

  if (gate.status === "account-error") {
    return (
      <AppScreen>
        <View style={styles.block}>
          <Text style={styles.title}>โหลดข้อมูลบัญชีไม่สำเร็จ</Text>
          <Notice title="ยังเข้าใช้งานไม่ได้" message={gate.message} />
          <Text style={styles.help}>
            ข้อมูลทีมและบทบาทของคุณยังไม่ถูกยืนยัน
            จึงยังเข้าพื้นที่นักกีฬาหรือโค้ชไม่ได้
          </Text>
          <PrimaryButton label="ลองอีกครั้ง" onPress={retry} />
          <PrimaryButton
            label="ออกจากระบบ"
            variant="quiet"
            onPress={() => {
              void signOut();
            }}
          />
        </View>
      </AppScreen>
    );
  }

  return (
    <AppScreen>
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} size="large" />
        <Text style={styles.help}>กำลังเตรียมข้อมูล</Text>
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  block: {
    gap: spacing.md,
    marginTop: spacing.xxl,
  },
  centered: {
    alignItems: "center",
    gap: spacing.md,
    marginTop: spacing.xxxl,
  },
  title: {
    color: colors.ink,
    fontSize: type.title,
    fontWeight: "800",
  },
  help: {
    color: colors.inkMuted,
    fontSize: type.small,
    lineHeight: 20,
  },
});
