<script setup>
defineProps({ name: { type: String, default: "chart" } });
const paths = {
  home: ["M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9"],
  risk: ["M12 3 2 21h20ZM12 9v5M12 17h.01"],
  catalog: ["M4 4h16v17H4ZM8 8h8M8 12h8M8 16h5"],
  settings: ["M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"],
  search: ["M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0"],
  sun: ["M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1M18 18l1 1M19 5l-1 1M6 18l-1 1"],
  moon: ["M21 13A9 9 0 0 1 11 3 9 9 0 1 0 21 13"],
  logout: ["M9 4H4v16h5M14 8l4 4-4 4M8 12h13"],
  menu: ["M4 6h16M4 12h16M4 18h16"],
  close: ["m6 6 12 12M6 18 18 6"],
  folder: [
    "M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z",
    "M3 10h18",
  ],
  tasks: [
    "M9 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4",
    "m8 12 3 3L21 5",
  ],
  shield: ["m12 3 8 3v6c0 5-8 9-8 9S4 17 4 12V6Z", "M12 8v5", "M12 17h.01"],
  clock: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18", "M12 7v5l3 2"],
  team: [
    "M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8",
    "M2 21v-2a6 6 0 0 1 12 0v2",
    "M16 4a4 4 0 0 1 0 8",
    "M22 21v-2a6 6 0 0 0-4-5.65",
  ],
  calendar: [
    "M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2",
    "M16 3v4M8 3v4M3 11h18",
    "M8 15h2M14 15h2",
  ],
  arrow: ["M5 12h14m-5-5 5 5-5 5"],
  left: ["m14 6-6 6 6 6"],
  right: ["m10 6 6 6-6 6"],
  refresh: [
    "M20 7v5h-5",
    "M4 17v-5h5",
    "M6.1 7a7 7 0 0 1 11.55-1L20 9M4 15l2.35 3A7 7 0 0 0 17.9 17",
  ],
  chart: ["M4 20h16", "M7 16V9M12 16V4M17 16v-5"],
  check: ["m5 12 4 4L19 6"],
};
const aliases = { projects: "folder", time: "clock", users: "team" };
</script>
<template>
  <svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path v-for="(path, index) in paths[aliases[name] || name] || paths.chart" :key="index" :d="path" />
  </svg>
</template>
<style scoped>
.ui-icon { display: block; width: 18px; height: 18px; flex-shrink: 0; }
</style>
