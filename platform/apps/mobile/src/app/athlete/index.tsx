import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { InfoCard } from "@/components/info-card";
import { PrimaryButton } from "@/components/primary-button";
import { ScreenHeading } from "@/components/screen-heading";
import { ROUTES } from "@/features/auth/gate";
import { DailyCheckInCard } from "@/features/check-in/check-in-card";
import { useAccountQuery } from "@/features/profile/use-account";
import { spacing } from "@/theme/tokens";

/**
 * The athlete shell.
 *
 * Reachable only while `canEnterRoleArea(gate, "athlete")` holds, which the
 * root layout enforces by removing this screen from the navigator otherwise.
 * The training and sleep content is still placeholder; TASK-013 replaces the
 * check-in placeholder with the real inline card and adds no route, so the
 * routing rules TASK-009 established are untouched.
 */
export default function AthleteTodayScreen() {
  const account = useAccountQuery();
  const router = useRouter();

  return (
    <AppScreen>
      <ScreenHeading
        eyebrow="สำหรับนักกีฬา"
        title="แผนของวันนี้"
        description={
          account.data?.displayName === null ||
          account.data?.displayName === undefined
            ? undefined
            : `สวัสดี ${account.data.displayName}`
        }
      />

      <InfoCard
        label="การซ้อม"
        title="ยังไม่มีแผนที่เผยแพร่"
        description="เมื่อโค้ชส่งแผน รายละเอียดการซ้อมวันนี้จะปรากฏตรงนี้"
        accent="primary"
      />
      <InfoCard
        label="การนอน"
        title="ยังไม่ได้เชื่อมต่อ"
        description="ข้อมูลการนอนจะต้องได้รับอนุญาตจากคุณก่อนนำมาแสดงหรือแชร์"
      />
      <DailyCheckInCard />

      <View style={styles.actions}>
        <PrimaryButton
          label="บัญชีของฉัน"
          variant="quiet"
          onPress={() => {
            router.push(ROUTES.profile);
          }}
        />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  actions: {
    gap: spacing.md,
    marginTop: spacing.lg,
  },
});
