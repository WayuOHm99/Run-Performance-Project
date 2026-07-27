import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { InfoCard } from "@/components/info-card";
import { PrimaryButton } from "@/components/primary-button";
import { ScreenHeading } from "@/components/screen-heading";
import { useAuth } from "@/features/auth/auth-provider";
import { ROUTES } from "@/features/auth/gate";
import { useRetryAccount } from "@/features/profile/use-account";
import { spacing } from "@/theme/tokens";

/**
 * Shown to a signed-in, onboarded user who holds no active membership.
 *
 * This covers both a brand-new account and a user whose membership was revoked.
 * They may edit their display name and sign out; no athlete or coach route
 * exists for them, because the guards in the root layout removed those screens
 * from the navigator entirely.
 *
 * This state is only ever reached from a *successful* load that returned no
 * active membership. A failed load goes to the retry state instead.
 */
export default function PendingScreen() {
  const { signOut } = useAuth();
  const retry = useRetryAccount();
  const router = useRouter();

  return (
    <AppScreen>
      <ScreenHeading
        title="ยังไม่ได้อยู่ในทีม"
        description="บัญชีของคุณพร้อมใช้งานแล้ว แต่ยังไม่มีทีมที่ใช้งานอยู่"
      />

      <View style={styles.block}>
        <InfoCard
          label="สถานะ"
          title="รอโค้ชเพิ่มคุณเข้าทีม"
          description="เมื่อโค้ชเพิ่มคุณเข้าทีมแล้ว พื้นที่นักกีฬาหรือโค้ชจะเปิดให้ใช้งานโดยอัตโนมัติ"
          accent="primary"
        />

        <PrimaryButton label="ตรวจสอบสถานะอีกครั้ง" onPress={retry} />
        <PrimaryButton
          label="แก้ไขชื่อที่ใช้แสดง"
          variant="quiet"
          onPress={() => {
            router.push(ROUTES.profile);
          }}
        />
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

const styles = StyleSheet.create({
  block: {
    gap: spacing.md,
    marginTop: spacing.lg,
  },
});
