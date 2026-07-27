import type { Href } from "expo-router";

export type PreviewRole = {
  id: "athlete" | "coach";
  title: string;
  description: string;
  actionLabel: string;
  route: Href;
};

export const roleOptions: readonly PreviewRole[] = [
  {
    id: "athlete",
    title: "นักกีฬา",
    description: "ดูแผนซ้อมวันนี้และพื้นที่สำหรับส่งข้อมูลหลังซ้อม",
    actionLabel: "ดู Athlete Today",
    route: "/athlete",
  },
  {
    id: "coach",
    title: "โค้ช",
    description: "ดูโครงภาพรวมทีม แผนซ้อม และธงที่ต้องติดตาม",
    actionLabel: "ดู Coach Team",
    route: "/coach",
  },
];
