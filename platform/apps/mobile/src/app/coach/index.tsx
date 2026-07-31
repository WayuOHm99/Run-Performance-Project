import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { InfoCard } from "@/components/info-card";
import { PrimaryButton } from "@/components/primary-button";
import { ScreenHeading } from "@/components/screen-heading";
import { ROUTES } from "@/features/auth/gate";
import { CoachCheckInReviewSection } from "@/features/coach-check-in/coach-check-in-section";
import { useAccountQuery } from "@/features/profile/use-account";
import { spacing } from "@/theme/tokens";

/**
 * The coach shell.
 *
 * Reachable only while `canEnterRoleArea(gate, "coach")` holds. An
 * athlete-only user has no route here at all, and would in any case see nothing
 * through RLS.
 *
 * TASK-016 replaced the Team placeholder with the read-only daily check-in
 * review. The monitoring-flags and training-plan placeholders are deliberately
 * unchanged: neither has a data contract yet, and inventing one here would put
 * an interpretation of health data on screen that no decision has approved.
 * No route, detail screen, or tab was added — this screen is still the only
 * coach surface.
 */
export default function CoachTeamScreen() {
  const account = useAccountQuery();
  const router = useRouter();

  return (
    <AppScreen>
      <ScreenHeading
        eyebrow="สำหรับโค้ช"
        title="ภาพรวมทีม"
        description={
          account.data?.displayName === null ||
          account.data?.displayName === undefined
            ? undefined
            : `สวัสดี ${account.data.displayName}`
        }
      />

      <CoachCheckInReviewSection />

      <InfoCard
        label="ธงเฝ้าระวัง"
        title="ไม่มีข้อมูลให้ประเมิน"
        description="ธงจะอธิบายเหตุผลอย่างชัดเจนและใช้ช่วยตัดสินใจ ไม่ใช่การวินิจฉัย"
      />
      <InfoCard
        label="แผนซ้อม"
        title="การสร้างแผนยังไม่เปิดใช้งาน"
        description="ฟังก์ชันสร้างและเผยแพร่แผนจะเพิ่มหลังระบบสิทธิ์และทีมผ่านการทดสอบ"
      />

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
