<script>
import { shallowReactive } from "vue";
const modalStack = shallowReactive([]);
let previousOverflow = "";
</script>
<script setup>
import {
  ref,
  computed,
  onMounted,
  onUpdated,
  onBeforeUnmount,
  nextTick,
  useId,
} from "vue";
defineProps({ title: String });
const emit = defineEmits(["close"]);
const box = ref();
const titleId = useId();
const entry = { id: Symbol("modal"), element: null };
const isTop = computed(() => modalStack.at(-1) === entry);
const level = ref(0);
let previous,
  alive = false;
function focusable(element) {
  return [
    ...element.querySelectorAll(
      'button,a[href],input,select,textarea,[tabindex]:not([tabindex="-1"])',
    ),
  ].filter(
    (node) =>
      !node.disabled &&
      !node.closest("[hidden],[inert]") &&
      getComputedStyle(node).display !== "none" &&
      getComputedStyle(node).visibility !== "hidden",
  );
}
function focusFirst(element = box.value) {
  (element && (focusable(element)[0] || element))?.focus();
}
function close() {
  if (isTop.value) emit("close");
}
function keyboard(event) {
  if (!isTop.value) return;
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopImmediatePropagation();
    close();
  } else if (event.key === "Tab") {
    const nodes = focusable(box.value),
      first = nodes[0],
      last = nodes.at(-1);
    if (!nodes.length) {
      event.preventDefault();
      box.value.focus();
    } else if (!box.value.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
}
function containFocus(event) {
  if (isTop.value && !box.value.contains(event.target)) focusFirst();
}
onMounted(async () => {
  alive = true;
  previous = document.activeElement;
  entry.element = box.value;
  if (!modalStack.length) {
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  level.value = modalStack.length;
  modalStack.push(entry);
  document.addEventListener("keydown", keyboard);
  document.addEventListener("focusin", containFocus);
  await nextTick();
  if (alive && isTop.value) focusFirst();
});

onUpdated(() => {
  if (alive && isTop.value && !box.value.contains(document.activeElement))
    focusFirst();
});
onBeforeUnmount(() => {
  alive = false;
  document.removeEventListener("keydown", keyboard);
  document.removeEventListener("focusin", containFocus);
  const wasTop = isTop.value,
    index = modalStack.indexOf(entry);
  if (index >= 0) modalStack.splice(index, 1);
  if (!modalStack.length) document.body.style.overflow = previousOverflow;
  if (wasTop)
    nextTick(() => {
      const top = modalStack.at(-1);
      if (previous?.isConnected && (!top || top.element.contains(previous)))
        previous.focus();
      else if (top) focusFirst(top.element);
    });
});
</script>
<template>
  <Teleport to="body">
    <div
      class="modal-overlay"
      :style="{ zIndex: 1000 + level }"
      :inert="!isTop || undefined"
      @click.self="close"
    >
      <section
        ref="box"
        class="modal"
        role="dialog"
        tabindex="-1"
        :aria-modal="isTop ? 'true' : undefined"
        :aria-hidden="!isTop ? 'true' : undefined"
        :aria-labelledby="titleId"
      >
        <header>
          <h2 :id="titleId">{{ title }}</h2>
          <button type="button" aria-label="Закрыть" @click="close">×</button>
        </header>
        <div class="modal-body"><slot /></div>
      </section>
    </div>
  </Teleport>
</template>
