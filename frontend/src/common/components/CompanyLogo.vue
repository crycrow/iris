<script setup>
import { useId } from "vue";
const clipId = useId();
defineProps({ label: { type: String, default: "Логотип компании" } });
</script>
<template>
  <svg
    class="company-logo"
    viewBox="0 0 1280 1280"
    role="img"
    :aria-label="label"
  >
    <defs>
      <clipPath :id="clipId">
        <path
          d="M72 220 Q72 163 119 158 Q153 151 179 192 L572 915 Q583 938 609 938 L652 938 Q676 938 692 908 L1103 195 Q1137 151 1172 163 Q1206 174 1206 213 L1206 803 Q1206 841 1175 864 L658 1203 Q622 1223 594 1201 L99 859 Q72 841 72 802Z"
        />
        <path
          d="M294 118 L582 73 Q613 68 642 73 L936 125 Q969 134 952 165 L765 480 Q751 499 729 499 L491 499 Q477 499 464 478 L277 163 Q263 130 294 118Z"
        />
        <path
          d="M550 579 L686 579 Q711 580 697 608 L632 722 Q618 744 605 724 L537 606 Q524 579 550 579Z"
        />
      </clipPath>
    </defs>
    <image
      href="/brand/company-logo-white.png"
      width="1280"
      height="1229"
      :clip-path="`url(#${clipId})`"
    />
  </svg>
</template>
<style scoped>
.company-logo {
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
}
.company-logo image {
  filter: brightness(0) invert(1);
}
</style>
