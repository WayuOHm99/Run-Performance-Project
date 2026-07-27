import { StyleSheet, View } from "react-native";

import { AppScreen } from "@/components/app-screen";
import { InfoCard } from "@/components/info-card";
import { PrimaryButton } from "@/components/primary-button";
import { ScreenHeading } from "@/components/screen-heading";
import { useAuth } from "@/features/auth/auth-provider";
import { spacing } from "@/theme/tokens";

/**
 * Shown when a sign-up returned no session.
 *
 * Deliberately generic: it never states whether the address was newly
 * registered or already had an account, because the difference between those
 * two answers is exactly what account enumeration is. The address itself is not
 * echoed back either.
 */
export default function CheckEmailScreen() {
  const { dismissEmailConfirmation } = useAuth();

  return (
    <AppScreen>
      <ScreenHeading
        title="ตรวจสอบอีเมลของคุณ"
        description="หากอีเมลนี้ใช้งานได้ เราได้ส่งลิงก์ยืนยันไปให้แล้ว"
      />

      <View style={styles.block}>
        <InfoCard
          label="ขั้นตอนถัดไป"
          title="ยืนยันอีเมลแล้วกลับมาเข้าสู่ระบบ"
          description="เปิดลิงก์ในอีเมลเพื่อยืนยันบัญชี จากนั้นกลับมาที่แอปแล้วเข้าสู่ระบบด้วยอีเมลและรหัสผ่านเดิม"
          accent="primary"
        />
        <InfoCard
          label="หมายเหตุ"
          title="ยังไม่มีบทบาทหรือทีม"
          description="บัญชีใหม่จะยังไม่มีบทบาทนักกีฬาหรือโค้ช จนกว่าโค้ชจะเพิ่มคุณเข้าทีม"
        />

        <PrimaryButton
          label="กลับไปหน้าเข้าสู่ระบบ"
          onPress={dismissEmailConfirmation}
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
