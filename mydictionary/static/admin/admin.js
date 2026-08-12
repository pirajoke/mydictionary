const navigation = document.querySelector(".nav-disclosure");

if (navigation) {
  const mobile = window.matchMedia("(max-width: 820px)");
  const syncNavigation = (matches) => {
    navigation.open = !matches;
  };

  syncNavigation(mobile.matches);
  mobile.addEventListener("change", (event) => syncNavigation(event.matches));
}
