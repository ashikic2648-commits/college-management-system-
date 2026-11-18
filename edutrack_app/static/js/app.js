document.addEventListener("DOMContentLoaded", () => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
  if (token) document.querySelectorAll("form").forEach(form => {
    if (!form.querySelector('[name=\"csrf_token\"]')) {
      const input = document.createElement("input");
      input.type = "hidden"; input.name = "csrf_token"; input.value = token;
      form.appendChild(input);
    }
  });
  const sidebar = document.querySelector("#sidebar");
  const shell = document.querySelector(".main-shell");
  document.querySelector("#sidebarToggle")?.addEventListener("click", () => {
    if (window.innerWidth <= 992) sidebar?.classList.toggle("open");
    else { sidebar?.classList.toggle("collapsed"); shell?.classList.toggle("expanded"); }
  });
  const departmentSelect = document.querySelector('select[name="department_id"]');
  const courseSelect = document.querySelector('select[name="course_id"]');
  if (departmentSelect && courseSelect) {
    const filterCourses = () => {
      [...courseSelect.options].forEach(option => {
        if (!option.value) return;
        option.hidden = option.dataset.department !== departmentSelect.value;
      });
      if (courseSelect.selectedOptions[0]?.hidden) courseSelect.value = "";
    };
    departmentSelect.addEventListener("change", filterCourses);
    filterCourses();
  }
  const signupRole = document.querySelector("#signupRole");
  const academicFields = document.querySelector("#academicFields");
  const departmentField = document.querySelector("#departmentField");
  const courseField = document.querySelector("#courseField");
  if (signupRole && academicFields) {
    const toggleAcademicFields = () => {
      const role = signupRole.value;
      academicFields.style.display = role === "admin" || role === "management" ? "none" : "grid";
      courseField.style.display = role === "student" ? "block" : "none";
      departmentField.style.display = role === "student" || role === "faculty" ? "block" : "none";
      const dept = departmentSelect;
      const course = courseSelect;
      if (dept) dept.required = role === "student" || role === "faculty";
      if (course) course.required = role === "student";
    };
    signupRole.addEventListener("change", toggleAcademicFields);
    toggleAcademicFields();
  }
  const facultyDepartment = document.querySelector("#facultyDepartment");
  const facultySubjects = document.querySelector("#facultySubjects");
  if (facultyDepartment && facultySubjects) {
    const filterFacultySubjects = () => {
      [...facultySubjects.options].forEach(option => {
        option.hidden = option.dataset.department !== facultyDepartment.value;
        if (option.hidden) option.selected = false;
      });
    };
    facultyDepartment.addEventListener("change", filterFacultySubjects);
    filterFacultySubjects();
  }
  document.querySelectorAll(".counter").forEach(counter => {
    const target = Number(counter.dataset.target || 0);
    const start = performance.now();
    const animate = now => {
      const progress = Math.min((now - start) / 700, 1);
      counter.textContent = Math.round(target * (1 - Math.pow(1-progress,3)));
      if (progress < 1) requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  });
  if (window.Chart && document.querySelector("#attendanceChart")) {
    new Chart(document.querySelector("#attendanceChart"), {type:"line",data:{labels:["Mon","Tue","Wed","Thu","Fri","Sat"],datasets:[{data:[72,78,75,82,window.edutrackStats.attendance,86],borderColor:"#4f46e5",backgroundColor:"rgba(79,70,229,.08)",fill:true,tension:.35}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,max:100,grid:{color:"#f1f5f9"}},x:{grid:{display:false}}}}});
    new Chart(document.querySelector("#performanceChart"), {type:"bar",data:{labels:["CSE","BBA","EEE"],datasets:[{data:[window.edutrackStats.marks,68,74],backgroundColor:["#6366f1","#3b82f6","#0891b2"],borderRadius:6}]},options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{beginAtZero:true,max:100,grid:{color:"#f1f5f9"}},x:{grid:{display:false}}}}});
  }
});
